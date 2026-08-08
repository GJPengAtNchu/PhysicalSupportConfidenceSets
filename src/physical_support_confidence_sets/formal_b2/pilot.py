"""One-shot development-pilot and frozen-ladder execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Iterable, Mapping

import numpy as np

from .bank import CandidateBank, PublicCandidate, build_candidate_bank
from .constants import ALPHA, DESIGN_LADDER, REGION_ORDER, SUPPORT_PATTERNS
from .controller import (
    PersistentOptionalAEBMapController,
    QueryReceipt,
    SealedQueryCapability,
)
from .data import generate_pilot_data, split_pilot_data
from .geometry import build_geometry
from .precision import (
    HighPrecisionReplay,
    deterministic_double_error_envelope,
)
from .projection import exact_oracle_projection, global_summary, projection_payload
from .scoring import (
    CalibrationLikelihoodCache,
    CandidateScoreTable,
    DeploymentLikelihoodCache,
    score_candidate_bank,
)
from .util import canonical_json, digest_json, sha256_file, hash_array


SCENE_ORDER = (
    "PERSISTENT_ONLY",
    "WEAK_C_PRESENT",
    "DETECTABLE_D_PRESENT_CONTROL",
)
INTENDED_WEAK_MAP = {
    "A": "FINE",
    "B": "SECTOR_SAFE",
    "C": "SUPPORT_AMBIGUOUS",
    "D": "ABSENT_ABOVE_BETA_MIN",
}
MAX_FEASIBILITY_QUERIES = 162


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical_json(dict(row)) + "\n")


def _memory_rss_bytes() -> tuple[int, str]:
    try:
        import psutil  # type: ignore

        info = psutil.Process().memory_info()
        if hasattr(info, "peak_wset"):
            return int(info.peak_wset), "psutil_peak_wset"
        return int(info.rss), "psutil_rss_current_fallback"
    except Exception as error:
        raise RuntimeError("psutil memory measurement is required") from error


class RuntimeCapExceeded(RuntimeError):
    pass


def _enforce_caps(
    *,
    total_started: float,
    phase_started: float | None = None,
    phase_cap_seconds: float | None = None,
    phase_name: str = "total",
) -> tuple[int, str]:
    now = time.perf_counter()
    if now - total_started > 2700.0:
        raise RuntimeCapExceeded("total development-pilot wall cap exceeded")
    if (
        phase_started is not None
        and phase_cap_seconds is not None
        and now - phase_started > phase_cap_seconds
    ):
        raise RuntimeCapExceeded(f"{phase_name} wall cap exceeded")
    memory, method = _memory_rss_bytes()
    if memory > 16 * 1024**3:
        raise RuntimeCapExceeded("16 GB development-pilot memory cap exceeded")
    return memory, method


@dataclass(frozen=True)
class LadderRow:
    row_id: str
    h: float
    calibration_size: int
    deployment_size: int
    tau_b: float
    tau_c: float
    tau_d_beta: float
    selection_order: int


@dataclass
class NumericalRegistry:
    pilot_id: str
    replay_records: dict[int, dict[str, Any]]
    disagreement_count: int = 0
    unsafe_disagreement_count: int = 0
    replay_seconds: float = 0.0
    replay_seconds_by_phase: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.replay_seconds_by_phase is None:
            self.replay_seconds_by_phase = {}

    def record(
        self,
        candidate_id: int,
        *,
        phase: str,
        reasons: Iterable[str],
        double_margin: float,
        hp: Any,
    ) -> None:
        row = self.replay_records.setdefault(
            int(candidate_id),
            {
                "candidate_id": int(candidate_id),
                "double_margin": float(double_margin),
                "high_precision_margin": hp.maximum_margin,
                "high_precision_margin_decimal": hp.maximum_margin_decimal,
                "double_survives": bool(double_margin <= 0.0),
                "high_precision_survives": bool(hp.survives),
                "decimal_digits": hp.decimal_digits,
                "phases": [],
                "reasons": [],
            },
        )
        if phase not in row["phases"]:
            row["phases"].append(phase)
        for reason in reasons:
            if reason not in row["reasons"]:
                row["reasons"].append(reason)
        if row["double_survives"] != row["high_precision_survives"]:
            row["classification_disagreement"] = True
            self.disagreement_count += int(
                not row.get("disagreement_previously_counted", False)
            )
            row["disagreement_previously_counted"] = True


@dataclass(frozen=True)
class PilotOutcome:
    row_id: str
    pilot_id: str
    scene: str
    pilot_number: int
    data_seed: int
    split_seed: int
    oracle_map: dict[str, str]
    controller_map: dict[str, str]
    plugin_map: dict[str, str]
    plugin_candidate_id: str
    query_count: int
    query_fraction: float
    controller_intended_matches: int
    unsafe_output_count: int
    possible_set_violation_count: int
    bound_violation_count: int
    numerical_disagreement_count: int
    unsafe_numerical_disagreement_count: int
    total_seconds: float
    controller_seconds: float
    oracle_seconds: float
    replay_seconds: float
    peak_rss_bytes: int
    artifact_directory: str


def frozen_ladder() -> tuple[LadderRow, ...]:
    return tuple(
        LadderRow(row_id, h, n, t, tau_b, tau_c, tau_d_beta, order)
        for (
            row_id,
            h,
            n,
            t,
            tau_b,
            tau_c,
            tau_d_beta,
            order,
        ) in DESIGN_LADDER
    )


def load_and_validate_development_seeds(path: Path) -> dict[str, list[dict[str, int]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != set(SCENE_ORDER):
        raise RuntimeError("D2 seed file must have exactly the three frozen scenes")
    forbidden = [
        key
        for key in payload
        if "primary" in key.lower() or "formal" in key.lower()
    ]
    if forbidden:
        raise RuntimeError(f"formal B2 primary seed material is forbidden: {forbidden}")
    normalized: dict[str, list[dict[str, int]]] = {}
    identities: set[tuple[int, int]] = set()
    for scene in SCENE_ORDER:
        rows = payload[scene]
        if not isinstance(rows, list) or len(rows) != 2:
            raise RuntimeError(f"{scene} must contain exactly two seed pairs")
        normalized[scene] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"data_seed", "split_seed"}:
                raise RuntimeError("seed pair has unexpected keys")
            if any(
                isinstance(row[key], bool)
                or not isinstance(row[key], int)
                or row[key] < 0
                for key in ("data_seed", "split_seed")
            ):
                raise RuntimeError("seed values must be nonnegative integers")
            identity = (int(row["data_seed"]), int(row["split_seed"]))
            if identity in identities:
                raise RuntimeError("duplicate D2 development seed pair")
            identities.add(identity)
            normalized[scene].append(
                {"data_seed": identity[0], "split_seed": identity[1]}
            )
    return normalized


def _score_payload(table: CandidateScoreTable, bank: CandidateBank) -> dict[str, Any]:
    return {
        "alpha": table.alpha,
        "threshold": math.log(1.0 / table.alpha),
        "proposal": asdict(table.proposal),
        "calibration_checkpoints": table.calibration_checkpoints.tolist(),
        "deployment_checkpoints": table.deployment_checkpoints.tolist(),
        "joint_checkpoints": [asdict(row) for row in table.joint_checkpoints],
        "candidate_count": len(bank.explanations),
        "double_survivor_count": int(np.sum(table.survives_all_checkpoints)),
        "margin_min": float(np.min(table.maximum_rejection_margin)),
        "margin_max": float(np.max(table.maximum_rejection_margin)),
        "margin_array_sha256": hash_array(table.maximum_rejection_margin),
        "checkpoint_log_e_array_sha256": hash_array(table.checkpoint_log_e),
        "roundoff_absolute_scale_sha256": hash_array(table.roundoff_absolute_scale),
    }


def _plugin_map(bank: CandidateBank, table: CandidateScoreTable) -> tuple[dict[str, str], dict[str, float], str]:
    explanation = bank.explanations[table.proposal.plugin_explanation_index]
    state = bank.dictionary_states[explanation.dictionary_index]
    support = bank.support_patterns[explanation.support_index]
    labels = {
        region: (
            "FINE"
            if region in support.regions
            else "ABSENT_ABOVE_BETA_MIN"
        )
        for region in REGION_ORDER
    }
    locations = {
        region: float(bank.geometry.atom(state.atom_id_for_region(region)).location)
        for region in support.regions
    }
    return labels, locations, explanation.candidate_id


def _unsafe_outputs(controller_map: Mapping[str, str], oracle_map: Mapping[str, str]) -> list[dict[str, str]]:
    safe_oracle = {
        "ABSENT_ABOVE_BETA_MIN": {"ABSENT_ABOVE_BETA_MIN"},
        "SUPPORT_AMBIGUOUS": {"SUPPORT_AMBIGUOUS"},
        "FINE": {"FINE"},
        "SECTOR_SAFE": {"SECTOR_SAFE", "FINE"},
        "LOCAL_AMBIGUOUS": {"LOCAL_AMBIGUOUS", "SECTOR_SAFE", "FINE"},
        "ABSTAIN": set(oracle_map.values()),
    }
    findings = []
    for region in REGION_ORDER:
        emitted = controller_map[region]
        truth = oracle_map[region]
        if emitted != "ABSTAIN" and truth not in safe_oracle[emitted]:
            findings.append({"region": region, "controller": emitted, "oracle": truth})
    return findings


def _audit_explanation_set_diameter(candidates: Iterable[object]) -> float:
    """Independently recompute the frozen finite-set diameter metric."""

    rows = tuple(candidates)
    if len(rows) <= 1:
        return 0.0
    diameter = 0.0
    for region in REGION_ORDER:
        presence = {region in set(getattr(candidate, "support")) for candidate in rows}
        if len(presence) > 1:
            return 1.0
        if presence == {True}:
            values = [float(getattr(candidate, "locations")[region]) for candidate in rows]
            diameter = max(diameter, max(values) - min(values))
    return float(diameter)


def _audit_trace_explanation_bounds(
    trace: Any,
    candidates: Iterable[object],
    exact_survivor_ids: Iterable[int],
) -> dict[str, Any]:
    """Audit every sealed prefix against the replay-aware exact survivor set.

    This is intentionally independent of the controller's bound constructor.
    It reconstructs lower/upper candidate sets solely from the public trace
    receipts, checks the serialized records, and verifies the finite-bank
    diameter sandwich at the initial prefix and after every logical query.
    """

    rows = tuple(candidates)
    by_id = {int(getattr(candidate, "candidate_id")): candidate for candidate in rows}
    if sorted(by_id) != list(range(1, len(rows) + 1)):
        raise RuntimeError("bound audit requires canonical candidate IDs")
    exact_ids = set(int(candidate_id) for candidate_id in exact_survivor_ids)
    if not exact_ids or not exact_ids.issubset(by_id):
        raise RuntimeError("bound audit received an invalid exact survivor set")
    exact_diameter = _audit_explanation_set_diameter(by_id[cid] for cid in exact_ids)
    statuses = {cid: "UNKNOWN" for cid in by_id}
    violations: list[dict[str, Any]] = []
    prefix_records: list[dict[str, Any]] = []

    def expected_snapshot() -> tuple[dict[str, Any], set[int], set[int]]:
        lower_ids = {cid for cid, status in statuses.items() if status == "ADMISSIBLE"}
        upper_ids = {cid for cid, status in statuses.items() if status != "REJECTED"}
        lower_diameter = _audit_explanation_set_diameter(
            by_id[cid] for cid in sorted(lower_ids)
        )
        upper_diameter = _audit_explanation_set_diameter(
            by_id[cid] for cid in sorted(upper_ids)
        )
        snapshot = {
            "finite_bank_size": len(rows),
            "lower_definition": "queried_ADMISSIBLE_witness_set",
            "upper_definition": "all_not_REJECTED_including_UNKNOWN_and_INDETERMINATE",
            "diameter_metric": (
                "max_over_regions_of_0_if_both_absent;absolute_location_difference_"
                "if_both_present;1_if_presence_differs"
            ),
            "lower_explanation_count": len(lower_ids),
            "upper_explanation_count": len(upper_ids),
            "lower_explanation_diameter": lower_diameter,
            "upper_explanation_diameter": upper_diameter,
            "lower_candidate_ids_sha256": digest_json(sorted(lower_ids)),
            "upper_candidate_ids_sha256": digest_json(sorted(upper_ids)),
        }
        return snapshot, lower_ids, upper_ids

    def audit_prefix(prefix: int, observed: Mapping[str, Any]) -> dict[str, Any]:
        expected, lower_ids, upper_ids = expected_snapshot()
        local: list[str] = []
        if dict(observed) != expected:
            local.append("serialized_bound_record_mismatch")
        if not lower_ids.issubset(exact_ids):
            local.append("lower_witness_not_in_exact_survivors")
        if not exact_ids.issubset(upper_ids):
            local.append("exact_survivor_missing_from_upper_possible_set")
        if expected["lower_explanation_diameter"] > exact_diameter + 1.0e-15:
            local.append("lower_diameter_exceeds_exact_diameter")
        if exact_diameter > expected["upper_explanation_diameter"] + 1.0e-15:
            local.append("exact_diameter_exceeds_upper_diameter")
        record = {
            "prefix_query_count": prefix,
            "lower_count": len(lower_ids),
            "upper_count": len(upper_ids),
            "lower_diameter": expected["lower_explanation_diameter"],
            "exact_diameter": exact_diameter,
            "upper_diameter": expected["upper_explanation_diameter"],
            "lower_subset_exact": lower_ids.issubset(exact_ids),
            "exact_subset_upper": exact_ids.issubset(upper_ids),
            "violation_reasons": local,
        }
        prefix_records.append(record)
        if local:
            violations.append(record)
        return expected

    previous = audit_prefix(0, trace.initial_global_explanation_bounds)
    seen: set[int] = set()
    for query_number, row in enumerate(trace.rows, start=1):
        if int(row.get("query_number", -1)) != query_number:
            violations.append(
                {"prefix_query_count": query_number, "violation_reasons": ["query_number_mismatch"]}
            )
        candidate_id = int(row["candidate_id"])
        if candidate_id in seen or statuses.get(candidate_id) != "UNKNOWN":
            violations.append(
                {"prefix_query_count": query_number, "violation_reasons": ["duplicate_or_noncanonical_query"]}
            )
        seen.add(candidate_id)
        if dict(row["pre_global_explanation_bounds"]) != previous:
            violations.append(
                {"prefix_query_count": query_number, "violation_reasons": ["pre_post_bound_discontinuity"]}
            )
        status = str(row["returned_status"])
        if status not in {"ADMISSIBLE", "REJECTED", "INDETERMINATE"}:
            violations.append(
                {"prefix_query_count": query_number, "violation_reasons": ["invalid_trace_status"]}
            )
        statuses[candidate_id] = status
        current = audit_prefix(query_number, row["post_global_explanation_bounds"])
        if (
            current["lower_explanation_count"] < previous["lower_explanation_count"]
            or current["upper_explanation_count"] > previous["upper_explanation_count"]
            or current["lower_explanation_diameter"]
            + 1.0e-15
            < previous["lower_explanation_diameter"]
            or current["upper_explanation_diameter"]
            > previous["upper_explanation_diameter"] + 1.0e-15
        ):
            violations.append(
                {"prefix_query_count": query_number, "violation_reasons": ["bound_monotonicity_violation"]}
            )
        previous = current
    if dict(trace.terminal_global_explanation_bounds) != previous:
        violations.append(
            {"prefix_query_count": len(trace.rows), "violation_reasons": ["terminal_bound_record_mismatch"]}
        )
    return {
        "metric": (
            "max_over_regions_of_0_if_both_absent;absolute_location_difference_"
            "if_both_present;1_if_presence_differs"
        ),
        "exact_survivor_count": len(exact_ids),
        "exact_survivor_ids_sha256": digest_json(sorted(exact_ids)),
        "exact_explanation_diameter": exact_diameter,
        "audited_prefix_count": len(prefix_records),
        "prefix_records": prefix_records,
        "violations": violations,
        "violation_count": len(violations),
        "verified": not violations,
    }


class _Classifier:
    def __init__(
        self,
        table: CandidateScoreTable,
        hp: HighPrecisionReplay,
        registry: NumericalRegistry,
        cap_guard: Any | None = None,
    ):
        self.table = table
        self.hp = hp
        self.registry = registry
        self.cap_guard = cap_guard
        self.receipts: dict[int, QueryReceipt] = {}

    def classify(
        self,
        candidate_id: int,
        reasons: tuple[str, ...],
        *,
        phase: str,
    ) -> QueryReceipt:
        cid = int(candidate_id)
        index = cid - 1
        margin = float(self.table.maximum_rejection_margin[index])
        envelope = deterministic_double_error_envelope(self.table, index)
        trigger_reasons: list[str] = []
        if margin <= 0.0:
            trigger_reasons.append("provisionally_admissible")
        if abs(margin) <= 0.02:
            trigger_reasons.append("absolute_margin_at_most_0.02")
        trigger_reasons.extend(
            reason
            for reason in reasons
            if reason.startswith("completes_")
            or reason in {
                "terminal_presence_absence_witness",
                "terminal_fine_sector_endpoint",
                "oracle_map_endpoint",
                "deterministic_far_audit",
                "sampled_group_elimination_reject",
            }
        )
        existing = self.receipts.get(cid)
        replay_needed = bool(trigger_reasons) and (
            existing is None or existing.precision != "mpmath_90_decimal"
        )
        if replay_needed:
            if self.cap_guard is not None:
                self.cap_guard()
            started = time.perf_counter()
            result = self.hp.replay(cid)
            elapsed = time.perf_counter() - started
            self.registry.replay_seconds += elapsed
            assert self.registry.replay_seconds_by_phase is not None
            self.registry.replay_seconds_by_phase[phase] = (
                self.registry.replay_seconds_by_phase.get(phase, 0.0) + elapsed
            )
            if self.cap_guard is not None:
                self.cap_guard()
            self.registry.record(
                cid,
                phase=phase,
                reasons=trigger_reasons,
                double_margin=margin,
                hp=result,
            )
            receipt = QueryReceipt(
                candidate_id=cid,
                status="ADMISSIBLE" if result.survives else "REJECTED",
                margin=result.maximum_margin,
                precision="mpmath_90_decimal",
                replay_reasons=tuple(sorted(set(trigger_reasons))),
                error_envelope=envelope,
            )
            self.receipts[cid] = receipt
            return receipt
        if existing is not None:
            if trigger_reasons and existing.precision == "mpmath_90_decimal":
                # A sealed 90-decimal classification is deterministic and is
                # reusable across later mandatory audit phases.  Record the
                # additional audit coverage without executing the numerical
                # replay a second time or silently under-reporting its cost.
                record = self.registry.replay_records.get(cid)
                if record is None:
                    raise RuntimeError(
                        "90-decimal receipt is missing its replay registry record"
                    )
                if phase not in record["phases"]:
                    record["phases"].append(phase)
                for reason in trigger_reasons:
                    if reason not in record["reasons"]:
                        record["reasons"].append(reason)
            return existing
        if margin - envelope <= 0.0:
            return QueryReceipt(cid, "INDETERMINATE", margin, "double_interval", (), envelope)
        receipt = QueryReceipt(cid, "REJECTED", margin, "double", (), envelope)
        self.receipts[cid] = receipt
        return receipt


def _deterministic_sample(pilot_id: str, ids: Iterable[int], count: int) -> list[int]:
    ranked = sorted(
        set(int(cid) for cid in ids),
        key=lambda cid: (
            hashlib.sha256(f"{pilot_id}|{cid}".encode("ascii")).digest(),
            cid,
        ),
    )
    return ranked[: max(0, int(count))]


def _serialize_elimination_group_identity(
    group: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and serialize the frozen tagged elimination-group identity."""

    group_type = group["group_type"]
    group_key = group["group_key"]
    member_candidate_ids = group["member_candidate_ids"]
    if not isinstance(group_key, str) or not group_key:
        raise ValueError("elimination-group key must be a nonempty string")
    if (
        not isinstance(member_candidate_ids, (list, tuple))
        or not member_candidate_ids
        or any(
            isinstance(candidate_id, bool)
            or not isinstance(candidate_id, int)
            or candidate_id <= 0
            for candidate_id in member_candidate_ids
        )
        or list(member_candidate_ids) != sorted(set(member_candidate_ids))
    ):
        raise ValueError(
            "elimination-group member_candidate_ids must be nonempty, unique, "
            "positive, and canonically ordered"
        )

    if group_type == "SUPPORT_PATTERN":
        if "region" in group:
            raise ValueError("SUPPORT_PATTERN forbids singular region")
        support_id = group["support_id"]
        support_index = group["support_index"]
        regions = group["regions"]
        if not isinstance(support_id, str) or not support_id:
            raise ValueError("SUPPORT_PATTERN support_id must be a nonempty string")
        if (
            isinstance(support_index, bool)
            or not isinstance(support_index, int)
            or not 0 <= support_index < len(SUPPORT_PATTERNS)
        ):
            raise ValueError("SUPPORT_PATTERN support_index is outside the frozen bank")
        if not isinstance(regions, (list, tuple)) or not regions:
            raise ValueError("SUPPORT_PATTERN regions must be a nonempty sequence")
        canonical_regions = tuple(region for region in REGION_ORDER if region in regions)
        if (
            any(region not in REGION_ORDER for region in regions)
            or len(set(regions)) != len(regions)
            or tuple(regions) != canonical_regions
        ):
            raise ValueError(
                "SUPPORT_PATTERN regions must be unique and in canonical region order"
            )
        expected_support_id, expected_regions = SUPPORT_PATTERNS[support_index]
        if support_id != expected_support_id or tuple(regions) != tuple(expected_regions):
            raise ValueError("SUPPORT_PATTERN identity differs from the frozen bank")
        return {
            "group_key": group_key,
            "group_type": group_type,
            "support_index": support_index,
            "support_id": support_id,
            "regions": list(regions),
            "member_candidate_ids": list(member_candidate_ids),
        }

    if group_type in {"SUPPORT_SIDE", "LOCAL_ENDPOINT"}:
        if "regions" in group:
            raise ValueError(f"{group_type} forbids plural regions")
        region = group["region"]
        if region not in REGION_ORDER:
            raise ValueError(f"{group_type} region is not canonical")
        return {
            "group_key": group_key,
            "group_type": group_type,
            "region": region,
            "member_candidate_ids": list(member_candidate_ids),
        }

    raise ValueError(f"unknown elimination-group type: {group_type!r}")


def _controller_group_audit(
    trace: Any, replayed_ids: Iterable[int]
) -> dict[str, Any]:
    """Certify sealed controller eliminations and define the 10% audit pool.

    The pool is deliberately restricted to queried REJECTED members of groups
    recorded as eliminated in the sealed trace.  It therefore cannot silently
    drift into a generic sample of controller rejects.
    """

    replayed = {int(cid) for cid in replayed_ids}
    rows_by_id = {
        int(row["candidate_id"]): row
        for row in trace.rows
    }
    closing_by_key: dict[str, int] = {}
    for row in trace.rows:
        for group in row.get("closed_groups", []):
            identity = _serialize_elimination_group_identity(group)
            closing_by_key[identity["group_key"]] = int(row["candidate_id"])

    certifications: list[dict[str, Any]] = []
    eligible_members: set[int] = set()
    for group in trace.eliminated_groups:
        identity = _serialize_elimination_group_identity(group)
        key = identity["group_key"]
        members = sorted({int(cid) for cid in group["member_candidate_ids"]})
        member_rows = [rows_by_id.get(cid) for cid in members]
        all_queried_rejected = all(
            row is not None and row["returned_status"] == "REJECTED"
            for row in member_rows
        )
        interval_certified = all(
            row is not None
            and row["returned_status"] == "REJECTED"
            and (
                row["precision"] == "mpmath_90_decimal"
                or (
                    row["precision"] == "double"
                    and float(row["margin"]) - float(row["error_envelope"]) > 0.0
                )
            )
            for row in member_rows
        )
        closing_id = closing_by_key.get(key)
        closing_row = rows_by_id.get(closing_id) if closing_id is not None else None
        closing_replayed = bool(
            closing_row is not None
            and closing_row["precision"] == "mpmath_90_decimal"
            and any(
                str(reason).startswith("completes_")
                for reason in closing_row.get("replay_reasons", [])
            )
        )
        if not (all_queried_rejected and interval_certified and closing_replayed):
            raise RuntimeError(f"uncertified controller group elimination: {key}")
        eligible_members.update(members)
        certifications.append(
            {
                **identity,
                "member_count": len(members),
                "closing_candidate_id": closing_id,
                "all_members_queried_rejected": all_queried_rejected,
                "remaining_double_margins_interval_certified": interval_certified,
                "closing_candidate_replayed_90_decimal": closing_replayed,
            }
        )

    queried_rejected = {
        int(row["candidate_id"])
        for row in trace.rows
        if row["returned_status"] == "REJECTED"
    }
    pool = sorted((eligible_members & queried_rejected) - replayed)
    return {
        "eliminated_group_count": len(certifications),
        "certifications": certifications,
        "all_eliminations_certified": all(
            row["all_members_queried_rejected"]
            and row["remaining_double_margins_interval_certified"]
            and row["closing_candidate_replayed_90_decimal"]
            for row in certifications
        ),
        "eligible_member_ids": sorted(eligible_members & queried_rejected),
        "remaining_audit_pool_ids": pool,
    }


def _far_audit_ids(
    pilot_id: str,
    margins: Iterable[float],
    mandatory_ids: Iterable[int],
    count: int = 16,
) -> list[int]:
    mandatory = {int(cid) for cid in mandatory_ids}
    pool = [
        index
        for index, margin in enumerate(margins, start=1)
        if abs(float(margin)) > 0.02 and index not in mandatory
    ]
    return _deterministic_sample(pilot_id, pool, count)


def _exact_group_definitions(candidates: Iterable[object]) -> list[dict[str, Any]]:
    """Frozen pattern, support-side, and location groups for oracle closure."""

    rows = tuple(candidates)
    groups: list[dict[str, Any]] = []
    for support_index, (support_id, regions) in enumerate(SUPPORT_PATTERNS):
        members = sorted(
            int(candidate.candidate_id)
            for candidate in rows
            if int(candidate.support_index) == support_index
        )
        groups.append(
            {
                "group_type": "SUPPORT_PATTERN",
                "group_key": f"SUPPORT_PATTERN:{support_id}",
                "support_index": support_index,
                "support_id": support_id,
                "regions": list(regions),
                "member_candidate_ids": members,
            }
        )
    for region in REGION_ORDER:
        for side, present in (("PRESENT", True), ("ABSENT", False)):
            members = sorted(
                int(candidate.candidate_id)
                for candidate in rows
                if (region in candidate.support) is present
            )
            if members:
                groups.append(
                    {
                        "group_type": "SUPPORT_SIDE",
                        "group_key": f"{region}:{side}",
                        "region": region,
                        "side": side,
                        "member_candidate_ids": members,
                    }
                )
        locations = sorted(
            {
                float(candidate.locations[region])
                for candidate in rows
                if region in candidate.support
            }
        )
        for location in locations:
            members = sorted(
                int(candidate.candidate_id)
                for candidate in rows
                if region in candidate.support
                and float(candidate.locations[region]) == location
            )
            groups.append(
                {
                    "group_type": "LOCAL_ENDPOINT",
                    "group_key": f"{region}:LOCATION:{location:.17g}",
                    "region": region,
                    "location": location,
                    "member_candidate_ids": members,
                }
            )
    return groups


def _oracle_snapshot(
    candidates: Iterable[object], receipts: Mapping[int, QueryReceipt]
) -> dict[str, Any]:
    indeterminate = sorted(
        cid for cid, receipt in receipts.items() if receipt.status == "INDETERMINATE"
    )
    if indeterminate:
        raise RuntimeError(
            f"exact oracle contains indeterminate candidates: {indeterminate[:8]}"
        )
    admissible = sorted(
        cid for cid, receipt in receipts.items() if receipt.status == "ADMISSIBLE"
    )
    projection = exact_oracle_projection(tuple(candidates), admissible)
    payload = projection_payload(projection)
    return {
        "admissible_ids": admissible,
        "projection": projection,
        "payload": payload,
        "map": {region: payload[region]["label"] for region in REGION_ORDER},
        "global_summary": global_summary(projection),
        "endpoint_ids": sorted(
            {
                cid
                for region in REGION_ORDER
                for cid in projection[region].endpoint_candidate_ids
            }
        ),
    }


def _certify_exact_eliminated_groups(
    groups: Iterable[Mapping[str, Any]],
    receipts: Mapping[int, QueryReceipt],
    replay_records: Mapping[int, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    certifications: list[dict[str, Any]] = []
    for group in groups:
        identity = _serialize_elimination_group_identity(group)
        members = [int(cid) for cid in group["member_candidate_ids"]]
        member_receipts = [receipts[cid] for cid in members]
        if not member_receipts or not all(
            row.status == "REJECTED" for row in member_receipts
        ):
            continue
        closing_id = members[-1]
        closing_record = replay_records.get(closing_id, {})
        expected_reason = (
            "completes_support_group_elimination"
            if group["group_type"] in {"SUPPORT_PATTERN", "SUPPORT_SIDE"}
            else "completes_local_endpoint_group_elimination"
        )
        closing_replayed = bool(
            receipts[closing_id].precision == "mpmath_90_decimal"
            and expected_reason in closing_record.get("reasons", [])
        )
        interval_certified = all(
            row.precision == "mpmath_90_decimal"
            or (
                row.precision == "double"
                and float(row.margin) - float(row.error_envelope) > 0.0
            )
            for row in member_receipts
        )
        if not (closing_replayed and interval_certified):
            raise RuntimeError(
                f"uncertified exact-oracle group elimination: {group['group_key']}"
            )
        certifications.append(
            {
                **identity,
                "member_count": len(members),
                "closing_candidate_id": closing_id,
                "closing_candidate_replayed_90_decimal": closing_replayed,
                "remaining_double_margins_interval_certified": interval_certified,
            }
        )
    return certifications


def run_pilot(
    row: LadderRow,
    *,
    scene: str,
    pilot_number: int,
    data_seed: int,
    split_seed: int,
    artifact_root: Path,
    calibration_cache: CalibrationLikelihoodCache | None = None,
    deployment_cache: DeploymentLikelihoodCache | None = None,
) -> PilotOutcome:
    pilot_id = f"{row.row_id}_{scene}_P{pilot_number:02d}"
    pilot_dir = artifact_root / "design_pilots" / row.row_id / pilot_id
    pilot_dir.mkdir(parents=True, exist_ok=False)
    total_started = time.perf_counter()
    rss_before, rss_method = _memory_rss_bytes()
    _enforce_caps(total_started=total_started)

    geometry = build_geometry(row.h)
    bank = build_candidate_bank(geometry)
    cal_cache = calibration_cache or CalibrationLikelihoodCache.from_bank(bank)
    dep_cache = deployment_cache or DeploymentLikelihoodCache.from_bank(
        bank,
        tau_b=row.tau_b,
        tau_c=row.tau_c,
        tau_d_beta=row.tau_d_beta,
    )
    data = generate_pilot_data(
        bank,
        scene,
        calibration_size=row.calibration_size,
        deployment_size=row.deployment_size,
        tau_b=row.tau_b,
        tau_c=row.tau_c,
        tau_d_beta=row.tau_d_beta,
        data_seed=data_seed,
    )
    splits = split_pilot_data(data, split_seed)
    score_started = time.perf_counter()
    scoring_timings: dict[str, float] = {}
    table = score_candidate_bank(
        bank,
        splits,
        cal_cache,
        dep_cache,
        alpha=ALPHA,
        timings=scoring_timings,
    )
    score_seconds = time.perf_counter() - score_started
    _enforce_caps(total_started=total_started)
    _write_json(
        pilot_dir / "data_manifest.json",
        {
            "pilot_id": pilot_id,
            "scene": scene,
            "calibration_shape": list(data.calibration.shape),
            "deployment_shape": list(data.deployment.shape),
            "calibration_sha256": hash_array(data.calibration),
            "deployment_sha256": hash_array(data.deployment),
            "calibration_proposal_indices_sha256": hash_array(splits.calibration.proposal_indices),
            "calibration_evaluation_indices_sha256": hash_array(splits.calibration.evaluation_indices),
            "deployment_proposal_indices_sha256": hash_array(splits.deployment.proposal_indices),
            "deployment_evaluation_indices_sha256": hash_array(splits.deployment.evaluation_indices),
            "calibration_snapshot_first_four": data.calibration[:4].tolist(),
            "deployment_snapshot_first_four": data.deployment[:4].tolist(),
        },
    )
    score_rows = [
        {
            "candidate_id": bank.explanations[i].candidate_id,
            "candidate_index": i,
            "dictionary_index": bank.explanations[i].dictionary_index,
            "support_index": bank.explanations[i].support_index,
            "maximum_margin": float(table.maximum_rejection_margin[i]),
            "maximum_checkpoint_index": int(table.maximum_checkpoint_index[i]),
            "double_survives": bool(table.survives_all_checkpoints[i]),
        }
        for i in range(len(bank.explanations))
    ]
    registry = NumericalRegistry(pilot_id, {})
    hp = HighPrecisionReplay(
        bank,
        splits,
        table,
        tau_b=row.tau_b,
        tau_c=row.tau_c,
        tau_d_beta=row.tau_d_beta,
    )
    public = bank.public_candidates()
    controller = PersistentOptionalAEBMapController(
        public,
        pilot_id,
        budget=0.75,
        proposal_candidate_id=table.proposal.plugin_explanation_index + 1,
        calibration_proposal_dictionary_index=(
            table.proposal.calibration_dictionary_index
        ),
    )

    controller_started = time.perf_counter()
    guard_state: dict[str, Any] = {
        "phase_started": controller_started,
        "phase_cap": 1800.0,
        "phase_name": "controller",
    }

    def cap_guard() -> None:
        _enforce_caps(
            total_started=total_started,
            phase_started=guard_state.get("phase_started"),
            phase_cap_seconds=guard_state.get("phase_cap"),
            phase_name=str(guard_state.get("phase_name", "total")),
        )

    classifier = _Classifier(table, hp, registry, cap_guard=cap_guard)
    capability = SealedQueryCapability(
        lambda cid, reasons: classifier.classify(cid, reasons, phase="controller")
    )
    trace = controller.run(capability)
    seal = trace.seal_trace()
    trace_payload = json.loads(seal.canonical_payload)
    trace_payload["trace_sha256"] = seal.trace_sha256
    trace_path = pilot_dir / "controller_trace.json"
    _write_json(trace_path, trace_payload)
    if hashlib.sha256(seal.canonical_payload.encode("utf-8")).hexdigest() != seal.trace_sha256:
        raise RuntimeError("controller trace seal failed before oracle opening")
    trace_file_sha = sha256_file(trace_path)
    _write_json(
        pilot_dir / "controller_trace_seal.json",
        {
            "pilot_id": pilot_id,
            "trace_sha256": seal.trace_sha256,
            "trace_file_sha256": trace_file_sha,
            "oracle_opened": False,
            "terminal_endpoint_candidate_ids": trace.terminal_endpoint_candidate_ids,
            "terminal_endpoint_audit_policy": "post_seal_pre_oracle_90_decimal_no_controller_feedback",
        },
    )

    # The sealed controller declares its canonical terminal endpoint IDs from
    # public possible-set geometry.  Replay those IDs only after the trace is
    # immutable and without feeding their results back into controller state.
    # This preserves unqueried-as-possible semantics and logical query cost
    # while satisfying the mandatory operational 90-decimal endpoint audit.
    terminal_endpoint_audit_ids = list(trace.terminal_endpoint_candidate_ids)
    for cid in terminal_endpoint_audit_ids:
        cap_guard()
        classifier.classify(
            cid,
            ("terminal_fine_sector_endpoint",),
            phase="controller_terminal_audit",
        )
    controller_seconds = time.perf_counter() - controller_started
    cap_guard()

    # Full-bank score summaries stay private until the trace seal above has
    # been independently verified and written.
    _write_json(pilot_dir / "score_manifest.json", _score_payload(table, bank))
    _write_jsonl(pilot_dir / "double_candidate_scores.jsonl", score_rows)

    # Exact oracle access is deliberately below the verified trace-seal gate.
    oracle_started = time.perf_counter()
    guard_state.update(
        phase_started=oracle_started,
        phase_cap=1800.0,
        phase_name="exact_oracle",
    )
    exact_groups = _exact_group_definitions(public)
    exact_groups_by_closer: dict[int, list[dict[str, Any]]] = {}
    for group in exact_groups:
        members = group["member_candidate_ids"]
        if members:
            exact_groups_by_closer.setdefault(int(members[-1]), []).append(group)
    final_receipts: dict[int, QueryReceipt] = {}
    for cid in range(1, len(bank.explanations) + 1):
        cap_guard()
        closing_groups = [
            group
            for group in exact_groups_by_closer.get(cid, [])
            if all(
                final_receipts[member].status == "REJECTED"
                for member in group["member_candidate_ids"][:-1]
            )
        ]
        reasons: list[str] = []
        if any(
            group["group_type"] in {"SUPPORT_PATTERN", "SUPPORT_SIDE"}
            for group in closing_groups
        ):
            reasons.append("completes_support_group_elimination")
        if any(group["group_type"] == "LOCAL_ENDPOINT" for group in closing_groups):
            reasons.append("completes_local_endpoint_group_elimination")
        final_receipts[cid] = classifier.classify(
            cid, tuple(reasons), phase="exact_oracle"
        )
    preliminary_oracle = _oracle_snapshot(public, final_receipts)
    oracle_seconds = time.perf_counter() - oracle_started
    cap_guard()

    # Offline publication audit: endpoints, terminal witnesses, all near
    # margins, 16 deterministic far candidates, and 10% of remaining queried
    # elimination rejects.
    offline_started = time.perf_counter()
    guard_state.update(phase_started=None, phase_cap=None, phase_name="offline_audit")
    initial_oracle_endpoint_ids = list(preliminary_oracle["endpoint_ids"])
    audited_oracle_endpoint_ids: set[int] = set()
    for cid in initial_oracle_endpoint_ids:
        cap_guard()
        classifier.classify(cid, ("oracle_map_endpoint",), phase="offline_audit")
        audited_oracle_endpoint_ids.add(cid)
    terminal_witnesses = sorted(
        row_["candidate_id"]
        for row_ in trace.rows
        if row_["returned_status"] == "ADMISSIBLE"
    )
    for cid in terminal_witnesses:
        cap_guard()
        classifier.classify(
            cid, ("terminal_presence_absence_witness",), phase="offline_audit"
        )
    near_ids = [
        i + 1
        for i, margin in enumerate(table.maximum_rejection_margin)
        if abs(float(margin)) <= 0.02
    ]
    for cid in near_ids:
        cap_guard()
        classifier.classify(cid, (), phase="offline_audit")

    # The 10% reject audit is defined only on members of groups proved
    # eliminated in the sealed controller trace.  Previously replayed members
    # are excluded before the deterministic ceiling and sample are applied.
    controller_group_audit = _controller_group_audit(
        trace, registry.replay_records.keys()
    )
    group_reject_pool = controller_group_audit["remaining_audit_pool_ids"]
    sample_count = math.ceil(0.10 * len(group_reject_pool)) if group_reject_pool else 0
    sampled_rejects = _deterministic_sample(
        pilot_id + "|group_reject", group_reject_pool, sample_count
    )
    for cid in sampled_rejects:
        cap_guard()
        classifier.classify(
            cid,
            ("sampled_group_elimination_reject",),
            phase="offline_audit",
        )

    # Far-audit candidates add coverage: they cannot duplicate any candidate
    # already replayed by the operational, endpoint, witness, near-margin,
    # group-closing, or group-reject policies.
    far_ids = _far_audit_ids(
        pilot_id,
        table.maximum_rejection_margin,
        registry.replay_records.keys(),
        16,
    )
    if len(far_ids) != 16:
        raise RuntimeError("fewer than 16 nonduplicating far-audit candidates")
    for cid in far_ids:
        cap_guard()
        classifier.classify(cid, ("deterministic_far_audit",), phase="offline_audit")

    # Rebuild the exact oracle from the final replay-aware receipts.  Auditing
    # an endpoint can expose a new survivor and hence a new endpoint, so repeat
    # until every endpoint of the refreshed map has itself been replayed.
    endpoint_fixed_point_iterations = 0
    while True:
        refreshed_receipts = {
            cid: classifier.receipts.get(cid, final_receipts[cid])
            for cid in range(1, len(bank.explanations) + 1)
        }
        refreshed_oracle = _oracle_snapshot(public, refreshed_receipts)
        new_endpoint_ids = sorted(
            set(refreshed_oracle["endpoint_ids"]) - audited_oracle_endpoint_ids
        )
        if not new_endpoint_ids:
            final_receipts = refreshed_receipts
            final_oracle = refreshed_oracle
            break
        endpoint_fixed_point_iterations += 1
        if endpoint_fixed_point_iterations > len(bank.explanations):
            raise RuntimeError("oracle endpoint replay failed to reach a fixed point")
        for cid in new_endpoint_ids:
            cap_guard()
            classifier.classify(
                cid, ("oracle_map_endpoint",), phase="offline_audit"
            )
            audited_oracle_endpoint_ids.add(cid)

    admissible_ids = final_oracle["admissible_ids"]
    oracle_projection = final_oracle["projection"]
    oracle_payload = final_oracle["payload"]
    oracle_map = final_oracle["map"]
    oracle_global_summary = final_oracle["global_summary"]
    endpoint_ids = final_oracle["endpoint_ids"]
    if not set(endpoint_ids).issubset(audited_oracle_endpoint_ids):
        raise RuntimeError("final oracle contains an unaudited endpoint")

    # Certify every exact-oracle group that remains eliminated after all
    # replay updates.  Its canonical closing candidate must have 90-decimal
    # replay and every other double reject must clear its deterministic bound.
    exact_group_certifications = _certify_exact_eliminated_groups(
        exact_groups, final_receipts, registry.replay_records
    )
    offline_audit_seconds = time.perf_counter() - offline_started
    cap_guard()

    controller_map = {
        region: trace.terminal_map[region]["label"] for region in REGION_ORDER
    }
    double_receipts = {
        cid: QueryReceipt(
            cid,
            "ADMISSIBLE" if bool(table.survives_all_checkpoints[cid - 1]) else "REJECTED",
            float(table.maximum_rejection_margin[cid - 1]),
            "double_unreplayed_counterfactual",
            (),
            deterministic_double_error_envelope(table, cid - 1),
        )
        for cid in range(1, len(bank.explanations) + 1)
    }
    double_oracle = _oracle_snapshot(public, double_receipts)
    double_unsafe = _unsafe_outputs(controller_map, double_oracle["map"])
    unsafe = _unsafe_outputs(controller_map, oracle_map)
    controller_rejected_ids = {
        int(row_["candidate_id"])
        for row_ in trace.rows
        if row_["returned_status"] == "REJECTED"
    }
    controller_upper_ids = set(range(1, len(bank.explanations) + 1)) - controller_rejected_ids
    possible_set_violations = sorted(set(admissible_ids) - controller_upper_ids)
    explanation_bound_audit = _audit_trace_explanation_bounds(
        trace, public, admissible_ids
    )
    bound_violations = explanation_bound_audit["violations"]
    double_unsafe_regions = {row["region"] for row in double_unsafe}
    unsafe_due_to_numerical = [
        row for row in unsafe if row["region"] not in double_unsafe_regions
    ]
    registry.unsafe_disagreement_count = len(unsafe_due_to_numerical)
    if unsafe or possible_set_violations or bound_violations:
        raise RuntimeError(
            "unsafe operational region output after replay-aware oracle: "
            f"{unsafe}; possible-set violations: {possible_set_violations}; "
            f"bound violations: {bound_violations[:4]}; "
            f"unsafe numerical disagreements: {unsafe_due_to_numerical}"
        )
    plugin_map, plugin_locations, plugin_candidate = _plugin_map(bank, table)
    intended_matches = sum(
        controller_map[region] == INTENDED_WEAK_MAP[region] for region in REGION_ORDER
    )
    query_count = len(trace.rows)
    rss_after, _ = _enforce_caps(total_started=total_started)
    total_seconds = time.perf_counter() - total_started
    runtime = {
        **scoring_timings,
        "total_score_pipeline_seconds": score_seconds,
        "controller_total_seconds": controller_seconds,
        "logical_candidate_queries": query_count,
        "unique_physical_evaluations": len(bank.explanations),
        "operational_high_precision_replays": sum(
            any(
                phase in {"controller", "controller_terminal_audit"}
                for phase in row["phases"]
            )
            for row in registry.replay_records.values()
        ),
        "exact_finite_bank_oracle_seconds": oracle_seconds,
        "offline_publication_audit_replays": sum(
            "offline_audit" in row["phases"] for row in registry.replay_records.values()
        ),
        "operational_high_precision_replay_seconds": (
            registry.replay_seconds_by_phase or {}
        ).get("controller", 0.0)
        + (registry.replay_seconds_by_phase or {}).get(
            "controller_terminal_audit", 0.0
        ),
        "terminal_endpoint_high_precision_replay_seconds": (
            registry.replay_seconds_by_phase or {}
        ).get("controller_terminal_audit", 0.0),
        "exact_oracle_high_precision_replay_seconds": (
            registry.replay_seconds_by_phase or {}
        ).get("exact_oracle", 0.0),
        "offline_high_precision_replay_seconds": (
            registry.replay_seconds_by_phase or {}
        ).get("offline_audit", 0.0),
        "offline_publication_audit_seconds": offline_audit_seconds,
        "all_high_precision_replay_seconds": registry.replay_seconds,
        "general_numerical_disagreement_count": registry.disagreement_count,
        "unsafe_numerical_disagreement_count": registry.unsafe_disagreement_count,
        "total_seconds": total_seconds,
        "peak_observed_rss_bytes": max(rss_before, rss_after),
        "memory_measurement": rss_method,
    }
    _write_json(
        pilot_dir / "oracle_map.json",
        {
            "pilot_id": pilot_id,
            "trace_sha256_gate": seal.trace_sha256,
            "trace_file_sha256_gate": trace_file_sha,
            "admissible_candidate_count": len(admissible_ids),
            "admissible_candidate_ids": admissible_ids,
            "region_map": oracle_payload,
            "global_summary": oracle_global_summary,
            "replay_reconciled": True,
            "endpoint_replay_fixed_point_iterations": endpoint_fixed_point_iterations,
        },
    )
    _write_json(
        pilot_dir / "plugin_singleton.json",
        {
            "pilot_id": pilot_id,
            "candidate_id": plugin_candidate,
            "region_map": plugin_map,
            "selected_locations": plugin_locations,
            "uncertainty_reported": False,
        },
    )
    numerical_payload = {
        "pilot_id": pilot_id,
        "decimal_digits": 90,
        "near_margin": 0.02,
        "initial_oracle_endpoint_ids": initial_oracle_endpoint_ids,
        "oracle_endpoint_ids": endpoint_ids,
        "all_audited_oracle_endpoint_ids": sorted(audited_oracle_endpoint_ids),
        "oracle_endpoint_replay_fixed_point_iterations": endpoint_fixed_point_iterations,
        "oracle_global_summary": oracle_global_summary,
        "terminal_controller_endpoint_ids": terminal_endpoint_audit_ids,
        "terminal_controller_endpoint_audit_after_trace_seal": True,
        "terminal_controller_endpoint_results_hidden_from_controller": True,
        "terminal_witness_ids": terminal_witnesses,
        "near_margin_ids": near_ids,
        "deterministic_far_ids": far_ids,
        "deterministic_far_ids_exclude_all_prior_mandatory_replays": True,
        "controller_eliminated_group_audit": controller_group_audit,
        "group_elimination_reject_audit_pool_ids": group_reject_pool,
        "group_elimination_reject_audit_pool_count": len(group_reject_pool),
        "group_elimination_reject_sample_fraction": 0.10,
        "group_elimination_reject_sample_target_count": sample_count,
        "sampled_group_elimination_reject_ids": sampled_rejects,
        "exact_oracle_eliminated_group_count": len(exact_group_certifications),
        "exact_oracle_group_certifications": exact_group_certifications,
        "all_exact_oracle_group_eliminations_certified": all(
            row["closing_candidate_replayed_90_decimal"]
            and row["remaining_double_margins_interval_certified"]
            for row in exact_group_certifications
        ),
        "replay_records": [registry.replay_records[cid] for cid in sorted(registry.replay_records)],
        "classification_disagreement_count": registry.disagreement_count,
        "general_classification_disagreement_count": registry.disagreement_count,
        "unsafe_disagreement_count": registry.unsafe_disagreement_count,
        "unsafe_numerical_disagreement_count": registry.unsafe_disagreement_count,
        "double_counterfactual_oracle_map": double_oracle["map"],
        "double_counterfactual_unsafe_outputs": double_unsafe,
        "final_replay_aware_unsafe_outputs": unsafe,
        "controller_upper_candidate_count": len(controller_upper_ids),
        "controller_upper_candidate_ids_sha256": digest_json(sorted(controller_upper_ids)),
        "replay_aware_oracle_survivor_subset_of_controller_upper": not possible_set_violations,
        "possible_set_violation_candidate_ids": possible_set_violations,
        "possible_set_violation_count": len(possible_set_violations),
        "global_explanation_bound_audit": explanation_bound_audit,
        "bound_violations": bound_violations,
        "bound_violation_count": len(bound_violations),
        "runtime": runtime,
    }
    _write_json(pilot_dir / "numerical_audit.json", numerical_payload)
    _write_json(pilot_dir / "runtime.json", runtime)
    _write_json(
        pilot_dir / "pilot_seal.json",
        {
            "pilot_id": pilot_id,
            "controller_trace_sha256": seal.trace_sha256,
            "oracle_map_sha256": sha256_file(pilot_dir / "oracle_map.json"),
            "numerical_audit_sha256": sha256_file(pilot_dir / "numerical_audit.json"),
            "scientific_result_observed": True,
            "rerun_allowed": False,
        },
    )
    return PilotOutcome(
        row_id=row.row_id,
        pilot_id=pilot_id,
        scene=scene,
        pilot_number=pilot_number,
        data_seed=data_seed,
        split_seed=split_seed,
        oracle_map=oracle_map,
        controller_map=controller_map,
        plugin_map=plugin_map,
        plugin_candidate_id=plugin_candidate,
        query_count=query_count,
        query_fraction=query_count / len(bank.explanations),
        controller_intended_matches=intended_matches,
        unsafe_output_count=len(unsafe),
        possible_set_violation_count=len(possible_set_violations),
        bound_violation_count=len(bound_violations),
        numerical_disagreement_count=registry.disagreement_count,
        unsafe_numerical_disagreement_count=registry.unsafe_disagreement_count,
        total_seconds=total_seconds,
        controller_seconds=controller_seconds,
        oracle_seconds=oracle_seconds,
        replay_seconds=registry.replay_seconds,
        peak_rss_bytes=max(rss_before, rss_after),
        artifact_directory=pilot_dir.as_posix(),
    )


def adjudicate_row(row: LadderRow, outcomes: list[PilotOutcome]) -> dict[str, Any]:
    if len(outcomes) != 6:
        raise ValueError("each evaluated D2 row requires exactly six pilots")
    if [outcome.scene for outcome in outcomes] != [
        scene for scene in SCENE_ORDER for _ in range(2)
    ]:
        raise ValueError("D2 pilot scene order differs from the frozen order")
    if [outcome.pilot_number for outcome in outcomes] != [1, 2, 1, 2, 1, 2]:
        raise ValueError("D2 pilot-number order differs from P01/P02")
    persistent = [p for p in outcomes if p.scene == "PERSISTENT_ONLY"]
    weak = [p for p in outcomes if p.scene == "WEAK_C_PRESENT"]
    controls = [
        p for p in outcomes if p.scene == "DETECTABLE_D_PRESENT_CONTROL"
    ]
    oracle_weak = all(p.oracle_map == INTENDED_WEAK_MAP for p in weak)
    controller_weak = all(p.controller_map == INTENDED_WEAK_MAP for p in weak)
    oracle_persistent = all(
        p.oracle_map["A"] == "FINE"
        and p.oracle_map["B"] in {"FINE", "SECTOR_SAFE"}
        and p.oracle_map["C"]
        in {"ABSENT_ABOVE_BETA_MIN", "SUPPORT_AMBIGUOUS"}
        and p.oracle_map["D"] == "ABSENT_ABOVE_BETA_MIN"
        for p in persistent
    )
    controller_persistent = all(
        p.controller_map["A"] == "FINE"
        and p.controller_map["B"] in {"FINE", "SECTOR_SAFE"}
        and p.controller_map["C"]
        in {"ABSENT_ABOVE_BETA_MIN", "SUPPORT_AMBIGUOUS", "ABSTAIN"}
        and p.controller_map["D"] == "ABSENT_ABOVE_BETA_MIN"
        for p in persistent
    )
    oracle_d_controls = all(
        p.oracle_map["D"] != "ABSENT_ABOVE_BETA_MIN" for p in controls
    )
    controller_d_controls = all(
        p.controller_map["D"]
        not in {"ABSENT_ABOVE_BETA_MIN", "ABSTAIN"}
        for p in controls
    )
    plugin_b_false_fine = all(
        p.plugin_map["B"] == "FINE" and p.oracle_map["B"] == "SECTOR_SAFE"
        for p in weak
    )
    plugin_c_definite = any(
        p.plugin_map["C"] in {"FINE", "ABSENT_ABOVE_BETA_MIN"}
        and p.oracle_map["C"] == "SUPPORT_AMBIGUOUS"
        for p in weak
    )
    controller_safe = all(p.unsafe_output_count == 0 for p in outcomes)
    possible_set_safe = all(
        p.possible_set_violation_count == 0 for p in outcomes
    )
    bounds_safe = all(p.bound_violation_count == 0 for p in outcomes)
    query_feasible = all(p.query_count <= MAX_FEASIBILITY_QUERIES for p in outcomes)
    numerical_safe = all(
        p.unsafe_numerical_disagreement_count == 0 for p in outcomes
    )
    runtime_ok = all(
        p.controller_seconds <= 1800
        and p.oracle_seconds <= 1800
        and p.total_seconds <= 2700
        and p.peak_rss_bytes <= 16 * 1024**3
        for p in outcomes
    )
    gates = {
        "oracle_weak_map": oracle_weak,
        "controller_weak_map": controller_weak,
        "oracle_persistent_map": oracle_persistent,
        "controller_persistent_map": controller_persistent,
        "oracle_d_present_controls_nonabsent": oracle_d_controls,
        "controller_d_present_controls_nonabsent_nonabstain": controller_d_controls,
        "plugin_b_false_fine_both_weak": plugin_b_false_fine,
        "plugin_c_definite_at_least_one_weak": plugin_c_definite,
        "controller_zero_unsafe": controller_safe,
        "possible_set_zero_violations": possible_set_safe,
        "bound_zero_violations": bounds_safe,
        "query_count_at_most_162_all_pilots": query_feasible,
        "numerical_zero_unsafe_classification_disagreement": numerical_safe,
        "runtime_and_memory_caps": runtime_ok,
    }
    return {
        "row": asdict(row),
        "gates": gates,
        "row_pass": all(gates.values()),
        "pilot_ids": [p.pilot_id for p in outcomes],
        "pilot_count": len(outcomes),
    }
