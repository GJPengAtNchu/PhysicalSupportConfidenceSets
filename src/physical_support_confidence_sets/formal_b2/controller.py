"""Score-blind persistent/optional controller for frozen B2-D2.1.

The controller sees only public candidate geometry and receipts for candidates
it has already selected.  In particular, the split-A proposal is used only to
rank dictionaries and to name the proposed A location; it is not a bootstrap
query and its score is never exposed to this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Callable, Mapping, Sequence

from .constants import (
    CONTROLLER_BUDGET_FRACTION,
    CONTROLLER_POLICY,
    CONTROLLER_QUERY_CAP,
    SUPPORT_PATTERNS,
)
from .projection import (
    COARSENESS_RANK,
    FINE_TOLERANCES,
    REGIONS,
    global_summary,
    projection_payload,
    safe_partial_projection,
)


VALID_RECEIPT_STATUSES = frozenset({"ADMISSIBLE", "REJECTED", "INDETERMINATE"})
WITNESS_SUPPORT_ORDER = (0, 1)  # AB, then ABC.
OBLIGATION_ORDER = (
    "A_NONPROPOSAL_LOCATION_ELIMINATION",
    "D_PRESENT_SIDE_ELIMINATION",
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _cid(candidate: object) -> int:
    return int(getattr(candidate, "candidate_id"))


def _support(candidate: object) -> frozenset[str]:
    return frozenset(getattr(candidate, "support"))


def _support_index(candidate: object) -> int:
    return int(getattr(candidate, "support_index"))


def _dictionary_index(candidate: object) -> int:
    return int(getattr(candidate, "dictionary_index"))


def _location(candidate: object, region: str) -> float:
    return float(getattr(candidate, "locations")[region])


def _explanation_set_diameter(candidates: Sequence[object]) -> float:
    """Exact frozen application diameter for a finite explanation set."""

    rows = tuple(candidates)
    if len(rows) <= 1:
        return 0.0
    diameter = 0.0
    for region in REGIONS:
        presence = {region in _support(candidate) for candidate in rows}
        if len(presence) > 1:
            return 1.0
        if presence == {True}:
            values = [_location(candidate, region) for candidate in rows]
            diameter = max(diameter, max(values) - min(values))
    return float(diameter)


@dataclass(frozen=True)
class QueryReceipt:
    candidate_id: int
    status: str
    margin: float
    precision: str
    replay_reasons: tuple[str, ...] = ()
    error_envelope: float = 0.0


@dataclass(frozen=True)
class TraceSeal:
    trace_sha256: str
    canonical_payload: str


@dataclass
class ControllerTrace:
    pilot_id: str
    bank_size: int
    budget_fraction: float
    budget_cap: int
    policy: str
    # Legacy bootstrap fields are retained so downstream trace readers remain
    # schema-compatible.  D2 freezes both to no-query values.
    bootstrap_candidate_id: int | None
    bootstrap_policy: str
    presence_tie_order: tuple[str, ...]
    proposal_candidate_id: int
    proposal_dictionary_index: int
    proposal_ranking_policy: str
    calibration_proposal_dictionary_index: int
    c_witness_seed_order: tuple[str, ...]
    initial_map: dict
    initial_global_summary: dict
    initial_global_explanation_bounds: dict
    rows: list[dict]
    terminal_map: dict
    terminal_global_summary: dict
    terminal_global_explanation_bounds: dict
    eliminated_groups: list[dict]
    terminal_endpoint_candidate_ids: list[int]
    stop_reason: str
    seal: TraceSeal | None = None

    def seal_trace(self) -> TraceSeal:
        if self.seal is None:
            payload = {
                "pilot_id": self.pilot_id,
                "bank_size": self.bank_size,
                "budget_fraction": self.budget_fraction,
                "budget_cap": self.budget_cap,
                "policy": self.policy,
                "bootstrap_candidate_id": self.bootstrap_candidate_id,
                "bootstrap_policy": self.bootstrap_policy,
                "presence_tie_order": list(self.presence_tie_order),
                "proposal_candidate_id": self.proposal_candidate_id,
                "proposal_dictionary_index": self.proposal_dictionary_index,
                "proposal_ranking_policy": self.proposal_ranking_policy,
                "calibration_proposal_dictionary_index": (
                    self.calibration_proposal_dictionary_index
                ),
                "c_witness_seed_order": list(self.c_witness_seed_order),
                "initial_map": self.initial_map,
                "initial_global_summary": self.initial_global_summary,
                "initial_global_explanation_bounds": self.initial_global_explanation_bounds,
                "rows": self.rows,
                "terminal_map": self.terminal_map,
                "terminal_global_summary": self.terminal_global_summary,
                "terminal_global_explanation_bounds": self.terminal_global_explanation_bounds,
                "eliminated_groups": self.eliminated_groups,
                "terminal_endpoint_candidate_ids": self.terminal_endpoint_candidate_ids,
                "stop_reason": self.stop_reason,
            }
            canonical = _canonical(payload)
            self.seal = TraceSeal(
                hashlib.sha256(canonical.encode("utf-8")).hexdigest(), canonical
            )
        return self.seal


class SealedQueryCapability:
    """One-way interface hiding every unqueried candidate result."""

    def __init__(self, query_backend: Callable[[int, tuple[str, ...]], QueryReceipt]):
        self._backend = query_backend
        self._queried: set[int] = set()
        self._sealed = False

    def query(self, candidate_id: int, reasons: tuple[str, ...]) -> QueryReceipt:
        if self._sealed:
            raise RuntimeError("query capability is sealed")
        if candidate_id in self._queried:
            raise RuntimeError("duplicate logical candidate query")
        receipt = self._backend(candidate_id, reasons)
        if receipt.candidate_id != candidate_id:
            raise RuntimeError("query receipt candidate mismatch")
        if receipt.status not in VALID_RECEIPT_STATUSES:
            raise RuntimeError("invalid query receipt status")
        self._queried.add(candidate_id)
        return receipt

    def seal(self) -> None:
        self._sealed = True


class PersistentOptionalAEBMapController:
    """Frozen ``PERSISTENT_OPTIONAL_AEB_MAP`` over the 216-candidate bank.

    Query selection is deterministic and score-free.  The two C support-side
    witnesses are sought first (AB then ABC).  Remaining candidate queries use
    the frozen shared-priority tuple::

        (-obligation_coverage, sum_remaining_sizes,
         -possible_coarseness_reduction, -possible_upper_diameter_reduction,
         candidate_id)

    Candidate-wise receipts are the only way a member leaves the possible
    set.  No completed group is inferred from a partial group.
    """

    def __init__(
        self,
        candidates: Sequence[object],
        pilot_id: str,
        budget: float = CONTROLLER_BUDGET_FRACTION,
        proposal_candidate_id: int | None = None,
        calibration_proposal_dictionary_index: int | None = None,
    ):
        if len(candidates) != 216:
            raise ValueError("frozen D2 controller requires exactly 216 candidates")
        ids = [_cid(candidate) for candidate in candidates]
        if ids != list(range(1, 217)):
            raise ValueError("D2 candidate IDs must be canonical 1..216")
        if not 0.0 < float(budget) <= CONTROLLER_BUDGET_FRACTION:
            raise ValueError("D2 controller budget must be in (0, 0.75]")
        if proposal_candidate_id is None:
            raise ValueError("D2 controller requires the split-A proposal ranking source")
        if calibration_proposal_dictionary_index is None:
            raise ValueError(
                "D2.1 controller requires the calibration split-A proposal dictionary"
            )

        self.candidates = tuple(candidates)
        self.by_id = {_cid(candidate): candidate for candidate in self.candidates}
        self.pilot_id = str(pilot_id)
        self.budget = float(budget)
        self.cap = math.floor(self.budget * len(self.candidates))
        if self.cap > CONTROLLER_QUERY_CAP:
            raise AssertionError("D2 controller cap exceeds the frozen 162 queries")
        self.statuses: dict[int, str] = {candidate_id: "UNKNOWN" for candidate_id in ids}

        value = int(proposal_candidate_id)
        if value not in self.by_id:
            raise ValueError("proposal candidate is outside the frozen D2 bank")
        self.proposal_candidate_id = value
        self.proposal_candidate = self.by_id[value]
        self.proposal_dictionary_index = _dictionary_index(self.proposal_candidate)
        self.proposal_a_location = _location(self.proposal_candidate, "A")
        calibration_value = int(calibration_proposal_dictionary_index)
        if not 0 <= calibration_value < 72:
            raise ValueError(
                "calibration proposal dictionary is outside the frozen D2.1 bank"
            )
        self.calibration_proposal_dictionary_index = calibration_value

        self._validate_public_bank()
        self.wrong_a_ids = frozenset(
            _cid(candidate)
            for candidate in self.candidates
            if abs(_location(candidate, "A") - self.proposal_a_location)
            > FINE_TOLERANCES["A"]
        )
        self.abd_ids = frozenset(
            _cid(candidate)
            for candidate in self.candidates
            if _support_index(candidate) == 2
        )
        if (
            len(self.wrong_a_ids),
            len(self.abd_ids),
            len(self.wrong_a_ids & self.abd_ids),
            len(self.wrong_a_ids | self.abd_ids),
        ) != (108, 72, 36, 144):
            raise AssertionError("frozen D2 wrong-A/ABD structural identity changed")

        self._group_definitions = self._build_group_definitions()

    def _validate_public_bank(self) -> None:
        seen: set[tuple[int, int]] = set()
        for candidate in self.candidates:
            dictionary_index = _dictionary_index(candidate)
            support_index = _support_index(candidate)
            if not 0 <= dictionary_index < 72 or not 0 <= support_index < 3:
                raise ValueError("candidate dictionary/support index is noncanonical")
            expected_id = dictionary_index * 3 + support_index + 1
            if _cid(candidate) != expected_id:
                raise ValueError("candidate ordering is not dictionary then AB/ABC/ABD")
            expected_support = frozenset(SUPPORT_PATTERNS[support_index][1])
            if _support(candidate) != expected_support:
                raise ValueError("candidate support differs from frozen AB/ABC/ABD bank")
            seen.add((dictionary_index, support_index))
        if len(seen) != 216:
            raise ValueError("candidate dictionary/support identities are not unique")

    def _build_group_definitions(self) -> dict[str, dict]:
        groups: dict[str, dict] = {}
        d_key = "D:PRESENT"
        groups[d_key] = {
            "group_type": "SUPPORT_SIDE",
            "group_key": d_key,
            "region": "D",
            "side": "PRESENT",
            "member_candidate_ids": sorted(self.abd_ids),
        }
        nonproposal = sorted(self.wrong_a_ids)
        nonproposal_locations = sorted(
            {
                _location(self.by_id[candidate_id], "A")
                for candidate_id in nonproposal
            }
        )
        if len(nonproposal_locations) != 1:
            raise AssertionError("D2 A must have exactly one nonproposal location")
        key = "A:NONPROPOSAL_LOCATION_ELIMINATION"
        groups[key] = {
            "group_type": "LOCAL_ENDPOINT",
            "group_key": key,
            "region": "A",
            "endpoint": "NONPROPOSAL",
            "location": nonproposal_locations[0],
            "member_candidate_ids": nonproposal,
        }
        return groups

    def _map(self, statuses: Mapping[int, str] | None = None) -> dict[str, object]:
        state = self.statuses if statuses is None else statuses
        return {
            region: safe_partial_projection(self.candidates, state, region)
            for region in REGIONS
        }

    @staticmethod
    def _payload(current: Mapping[str, object]) -> dict:
        return projection_payload(current)  # type: ignore[arg-type]

    def _possible_candidates(
        self, statuses: Mapping[int, str] | None = None
    ) -> tuple[object, ...]:
        state = self.statuses if statuses is None else statuses
        return tuple(
            candidate
            for candidate in self.candidates
            if state[_cid(candidate)] != "REJECTED"
        )

    def _global_explanation_bounds(
        self, statuses: Mapping[int, str] | None = None
    ) -> dict[str, object]:
        state = self.statuses if statuses is None else statuses
        lower_ids = sorted(
            candidate_id
            for candidate_id, status in state.items()
            if status == "ADMISSIBLE"
        )
        upper_ids = sorted(
            candidate_id
            for candidate_id, status in state.items()
            if status != "REJECTED"
        )
        lower = tuple(self.by_id[candidate_id] for candidate_id in lower_ids)
        upper = tuple(self.by_id[candidate_id] for candidate_id in upper_ids)
        return {
            "finite_bank_size": len(self.candidates),
            "lower_definition": "queried_ADMISSIBLE_witness_set",
            "upper_definition": "all_not_REJECTED_including_UNKNOWN_and_INDETERMINATE",
            "diameter_metric": (
                "max_over_regions_of_0_if_both_absent;absolute_location_difference_"
                "if_both_present;1_if_presence_differs"
            ),
            "lower_explanation_count": len(lower_ids),
            "upper_explanation_count": len(upper_ids),
            "lower_explanation_diameter": _explanation_set_diameter(lower),
            "upper_explanation_diameter": _explanation_set_diameter(upper),
            "lower_candidate_ids_sha256": hashlib.sha256(
                _canonical(lower_ids).encode("utf-8")
            ).hexdigest(),
            "upper_candidate_ids_sha256": hashlib.sha256(
                _canonical(upper_ids).encode("utf-8")
            ).hexdigest(),
        }

    def _terminal_endpoint_ids(self, terminal: Mapping[str, object]) -> list[int]:
        ids: set[int] = set()
        for region in REGIONS:
            state = terminal[region]
            if getattr(state, "label") not in {"FINE", "SECTOR_SAFE"}:
                continue
            upper_locations = tuple(getattr(state, "upper_locations"))
            if not upper_locations:
                continue
            for location in {upper_locations[0], upper_locations[-1]}:
                members = sorted(
                    _cid(candidate)
                    for candidate in self.candidates
                    if self.statuses[_cid(candidate)] != "REJECTED"
                    and region in _support(candidate)
                    and _location(candidate, region) == location
                )
                if members:
                    ids.add(members[0])
        return sorted(ids)

    def _dictionary_rank(self, candidate: object) -> tuple[int, int]:
        # The only D2.1 policy change: deployment proposal first, the distinct
        # calibration proposal second, then the inherited canonical remainder.
        # Both dictionary identities are frozen split-A inputs; no score,
        # truth, oracle map, or unqueried receipt participates in this ranking.
        dictionary_index = _dictionary_index(candidate)
        if dictionary_index == self.proposal_dictionary_index:
            seed_rank = 0
        elif dictionary_index == self.calibration_proposal_dictionary_index:
            seed_rank = 1
        else:
            seed_rank = 2
        return seed_rank, _cid(candidate)

    def _witness_action(self) -> tuple[int, str, str] | None:
        # The stage order is frozen: AB absent-side witness, then ABC
        # present-side witness.  A side is exhausted only after every member
        # has received a non-admissible receipt; no partial group inference is
        # made.
        for support_index, objective in (
            (0, "C_ABSENT_WITNESS"),
            (1, "C_PRESENT_WITNESS"),
        ):
            members = [
                candidate
                for candidate in self.candidates
                if _support_index(candidate) == support_index
            ]
            if any(
                self.statuses[_cid(candidate)] == "ADMISSIBLE"
                for candidate in members
            ):
                continue
            eligible = [
                candidate
                for candidate in members
                if self.statuses[_cid(candidate)] == "UNKNOWN"
            ]
            if eligible:
                selected = min(eligible, key=self._dictionary_rank)
                return _cid(selected), objective, SUPPORT_PATTERNS[support_index][0]
        return None

    def _unresolved_obligations(
        self, current: Mapping[str, object]
    ) -> dict[str, frozenset[int]]:
        obligations: dict[str, frozenset[int]] = {}
        if getattr(current["A"], "label") == "ABSTAIN":
            remaining_a = frozenset(
                candidate_id
                for candidate_id in self.wrong_a_ids
                if self.statuses[candidate_id] != "REJECTED"
            )
            if remaining_a:
                obligations["A_NONPROPOSAL_LOCATION_ELIMINATION"] = remaining_a
        if getattr(current["D"], "label") == "ABSTAIN":
            remaining_d = frozenset(
                candidate_id
                for candidate_id in self.abd_ids
                if self.statuses[candidate_id] != "REJECTED"
            )
            if remaining_d:
                obligations["D_PRESENT_SIDE_ELIMINATION"] = remaining_d
        return obligations

    @staticmethod
    def _coarseness_score(current: Mapping[str, object]) -> int:
        return sum(COARSENESS_RANK[getattr(current[region], "label")] for region in REGIONS)

    def _shared_action(
        self, current: Mapping[str, object]
    ) -> tuple[int, tuple[str, ...], tuple[object, ...]] | None:
        obligations = self._unresolved_obligations(current)
        if not obligations:
            return None
        current_coarseness = self._coarseness_score(current)
        current_diameter = _explanation_set_diameter(self._possible_candidates())
        ranked: list[tuple[tuple[object, ...], int, tuple[str, ...]]] = []
        for candidate in self.candidates:
            candidate_id = _cid(candidate)
            if self.statuses[candidate_id] != "UNKNOWN":
                continue
            covered = tuple(
                obligation
                for obligation in OBLIGATION_ORDER
                if obligation in obligations and candidate_id in obligations[obligation]
            )
            if not covered:
                continue
            hypothetical = dict(self.statuses)
            hypothetical[candidate_id] = "REJECTED"
            after_map = self._map(hypothetical)
            coarseness_reduction = self._coarseness_score(after_map) - current_coarseness
            after_diameter = _explanation_set_diameter(
                self._possible_candidates(hypothetical)
            )
            diameter_reduction = current_diameter - after_diameter
            remaining_size_sum = sum(len(obligations[name]) for name in covered)
            key: tuple[object, ...] = (
                -len(covered),
                remaining_size_sum,
                -coarseness_reduction,
                -diameter_reduction,
                candidate_id,
            )
            ranked.append((key, candidate_id, covered))
        if not ranked:
            return None
        key, candidate_id, covered = min(ranked, key=lambda row: row[0])
        return candidate_id, covered, key

    def _groups_closed_by_rejection(self, candidate_id: int) -> list[dict]:
        closed: list[dict] = []
        for group in self._group_definitions.values():
            members = group["member_candidate_ids"]
            if candidate_id not in members:
                continue
            if all(self.statuses[member] == "REJECTED" for member in members):
                closed.append(group)
        return sorted(closed, key=lambda row: str(row["group_key"]))

    def _groups_predicted_by_rejection(self, candidate_id: int) -> list[dict]:
        predicted: list[dict] = []
        for group in self._group_definitions.values():
            members = group["member_candidate_ids"]
            if candidate_id not in members:
                continue
            if all(
                member == candidate_id or self.statuses[member] == "REJECTED"
                for member in members
            ):
                predicted.append(group)
        return sorted(predicted, key=lambda row: str(row["group_key"]))

    def _append_query_row(
        self,
        *,
        capability: SealedQueryCapability,
        rows: list[dict],
        eliminated_groups: list[dict],
        eliminated_group_keys: set[str],
        candidate_id: int,
        action_type: str,
        target_region: str,
        reasons: tuple[str, ...],
        priority_key: tuple[object, ...] | None,
        covered_obligations: tuple[str, ...],
    ) -> None:
        before_state = self._map()
        before_bounds = self._global_explanation_bounds()
        predicted_closures = self._groups_predicted_by_rejection(candidate_id)
        reason_list = list(reasons)
        if any(
            group["group_type"] in {"SUPPORT_PATTERN", "SUPPORT_SIDE"}
            for group in predicted_closures
        ):
            reason_list.append("completes_support_group_elimination")
        if any(
            group["group_type"] == "LOCAL_ENDPOINT"
            for group in predicted_closures
        ):
            reason_list.append("completes_local_endpoint_group_elimination")
        receipt = capability.query(candidate_id, tuple(reason_list))
        self.statuses[candidate_id] = receipt.status
        closed_now: list[dict] = []
        if receipt.status == "REJECTED":
            for group in self._groups_closed_by_rejection(candidate_id):
                key = str(group["group_key"])
                if key not in eliminated_group_keys:
                    eliminated_group_keys.add(key)
                    eliminated_groups.append(group)
                    closed_now.append(group)
        after_state = self._map()
        rows.append(
            {
                "query_number": len(rows) + 1,
                "action_type": action_type,
                "target_region": target_region,
                "candidate_id": candidate_id,
                "returned_status": receipt.status,
                "margin": receipt.margin,
                "precision": receipt.precision,
                "replay_reasons": list(receipt.replay_reasons),
                "error_envelope": receipt.error_envelope,
                "covered_obligations": list(covered_obligations),
                "priority_key": None if priority_key is None else list(priority_key),
                "closed_groups": closed_now,
                "pre_map": self._payload(before_state),
                "post_map": self._payload(after_state),
                "pre_global_summary": global_summary(before_state),
                "post_global_summary": global_summary(after_state),
                "pre_global_explanation_bounds": before_bounds,
                "post_global_explanation_bounds": self._global_explanation_bounds(),
            }
        )

    def run(self, capability: SealedQueryCapability) -> ControllerTrace:
        initial = self._map()
        initial_bounds = self._global_explanation_bounds()
        rows: list[dict] = []
        eliminated_groups: list[dict] = []
        eliminated_group_keys: set[str] = set()
        stop_reason = "NO_ALLOWED_QUERY"

        while len(rows) < self.cap:
            current = self._map()
            if all(getattr(current[region], "label") != "ABSTAIN" for region in REGIONS):
                stop_reason = "ALL_REGIONS_TERMINAL"
                break

            witness = self._witness_action()
            if witness is not None:
                candidate_id, objective, support_id = witness
                self._append_query_row(
                    capability=capability,
                    rows=rows,
                    eliminated_groups=eliminated_groups,
                    eliminated_group_keys=eliminated_group_keys,
                    candidate_id=candidate_id,
                    action_type="C_SUPPORT_WITNESS",
                    target_region="C",
                    reasons=(
                        "controller_query",
                        "c_support_witness",
                        objective.lower(),
                        f"support_pattern_{support_id.lower()}",
                    ),
                    priority_key=None,
                    covered_obligations=(objective,),
                )
                continue

            shared = self._shared_action(current)
            if shared is not None:
                candidate_id, obligations, priority_key = shared
                reason_list = [
                    "controller_query",
                    "shared_elimination",
                    *(name.lower() for name in obligations),
                ]
                self._append_query_row(
                    capability=capability,
                    rows=rows,
                    eliminated_groups=eliminated_groups,
                    eliminated_group_keys=eliminated_group_keys,
                    candidate_id=candidate_id,
                    action_type="SHARED_ELIMINATION",
                    target_region="A+D" if len(obligations) == 2 else obligations[0][0],
                    reasons=tuple(reason_list),
                    priority_key=priority_key,
                    covered_obligations=obligations,
                )
                continue

            # B is already terminal at SECTOR_SAFE.  Its local refinement is
            # optional and cannot justify querying after an unresolved
            # mandatory certificate has no unqueried member.  Fail closed.
            stop_reason = "NO_ALLOWED_QUERY"
            break
        else:
            stop_reason = "BUDGET_EXHAUSTED"

        capability.seal()
        terminal_state = self._map()
        trace = ControllerTrace(
            pilot_id=self.pilot_id,
            bank_size=len(self.candidates),
            budget_fraction=self.budget,
            budget_cap=self.cap,
            policy=CONTROLLER_POLICY,
            bootstrap_candidate_id=None,
            bootstrap_policy="none_no_bootstrap_query",
            presence_tie_order=("C_AB", "C_ABC", *OBLIGATION_ORDER),
            proposal_candidate_id=self.proposal_candidate_id,
            proposal_dictionary_index=self.proposal_dictionary_index,
            proposal_ranking_policy=(
                "deployment_dictionary_then_distinct_calibration_dictionary_"
                "then_inherited_canonical_candidate_id"
            ),
            calibration_proposal_dictionary_index=(
                self.calibration_proposal_dictionary_index
            ),
            c_witness_seed_order=(
                "deployment_proposal_dictionary",
                "calibration_proposal_dictionary_if_distinct",
                "inherited_remaining_order",
            ),
            initial_map=self._payload(initial),
            initial_global_summary=global_summary(initial),
            initial_global_explanation_bounds=initial_bounds,
            rows=rows,
            terminal_map=self._payload(terminal_state),
            terminal_global_summary=global_summary(terminal_state),
            terminal_global_explanation_bounds=self._global_explanation_bounds(),
            eliminated_groups=eliminated_groups,
            terminal_endpoint_candidate_ids=self._terminal_endpoint_ids(terminal_state),
            stop_reason=stop_reason,
        )
        trace.seal_trace()
        return trace
