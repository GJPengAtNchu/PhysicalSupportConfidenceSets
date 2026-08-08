"""Stage-B complete finite-bank enumeration and structural audit.

This module is intentionally not imported by the controller-stage package.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import math
import time
from typing import Any

import numpy as np

from .constants import (
    FAR_AUDIT_COUNT,
    NEAR_THRESHOLD,
    PROFILE_PARAMETERS,
    PROFILES,
)
from .controller_stage import HiddenScoreBackend
from .science import CaseBundle
from .util import digest_json


def _hp_survives(record: dict[str, Any], alpha: float) -> bool:
    threshold = (Decimal(1) / Decimal(repr(float(alpha)))).ln()
    return max(Decimal(str(value)) for value in record["log_e"]) <= threshold


def _candidate_survives(
    candidate: dict[str, Any], alpha: float
) -> bool:
    high_precision = candidate.get("high_precision")
    if high_precision is not None:
        return _hp_survives(high_precision, alpha)
    return max(candidate["log_e"]) <= math.log(1.0 / alpha)


def _diameter(
    bundle: CaseBundle,
    candidates: list[dict[str, Any]],
    survivor_ids: set[int],
) -> tuple[float, list[str | int]]:
    proposal_phi = float(bundle.run.proposal.raw[0])
    points: list[tuple[str | int, float]] = [("PROPOSAL", proposal_phi)]
    seen = {proposal_phi}
    for row in candidates:
        if row["candidate_id"] not in survivor_ids:
            continue
        phi = float(row["raw"][0])
        if phi in seen:
            continue
        seen.add(phi)
        points.append((int(row["candidate_id"]), phi))
    if len(points) == 1:
        return 0.0, ["PROPOSAL"]
    best = -1.0
    endpoints: tuple[str | int, str | int] | None = None
    for left in range(len(points)):
        for right in range(left + 1, len(points)):
            distance = bundle.metric.distance(
                points[left][1], points[right][1]
            )
            pair = (points[left][0], points[right][0])
            if (
                distance > best + 1.0e-16
                or (
                    abs(distance - best) <= 1.0e-16
                    and repr(pair) < repr(endpoints)
                )
            ):
                best = float(distance)
                endpoints = pair
    assert endpoints is not None
    return best, [endpoints[0], endpoints[1]]


def _oracle_label(diameter: float, d_shell: float, profile: str) -> str:
    _, delta_f_fraction, delta_s_fraction = PROFILE_PARAMETERS[profile]
    if diameter <= delta_f_fraction * d_shell:
        return "ORACLE_FINE"
    if diameter <= delta_s_fraction * d_shell:
        return "ORACLE_SECTOR"
    return "ORACLE_AMBIGUOUS"


def _truth_radius(
    bundle: CaseBundle,
    candidates: list[dict[str, Any]],
    survivor_ids: set[int],
) -> float:
    values = [bundle.metric.distance(0.0, float(bundle.run.proposal.raw[0]))]
    values.extend(
        bundle.metric.distance(0.0, float(row["raw"][0]))
        for row in candidates
        if row["candidate_id"] in survivor_ids
    )
    return max(values)


def enumerate_oracle(
    bundle: CaseBundle,
    controller_traces: list[dict[str, Any]],
    *,
    workers: int = 4,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = time.monotonic()
    checkpoints = np.asarray(bundle.eprocess.checkpoints, dtype=int)

    def evaluate(candidate_id: int) -> dict[str, Any]:
        candidate = bundle.bank.candidate(candidate_id)
        values, gradient, hessian = (
            bundle.eprocess.evaluate_finite_bank_raw(
                np.asarray(candidate.raw, dtype=float), derivatives=False
            )
        )
        if gradient is not None or hessian is not None:
            raise ArithmeticError("oracle score returned derivatives")
        array = np.asarray(values, dtype=float)
        if array.shape != checkpoints.shape or not np.all(np.isfinite(array)):
            raise ArithmeticError("oracle score is invalid")
        maximum_index = int(np.argmax(array))
        return {
            "case_id": bundle.case_id,
            "candidate_id": candidate_id,
            "raw": list(candidate.raw),
            "x": list(candidate.x),
            "log_e": [float(value) for value in array],
            "maximum_log_e_double": float(array[maximum_index]),
            "maximum_checkpoint": int(checkpoints[maximum_index]),
            "high_precision": None,
            "replay_reasons": [],
        }

    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 8))) as pool:
        candidates = list(pool.map(evaluate, range(len(bundle.bank))))
    if [row["candidate_id"] for row in candidates] != list(
        range(len(bundle.bank))
    ):
        raise ArithmeticError("oracle candidate enumeration is incomplete")
    elapsed_after_double = time.monotonic() - started
    if elapsed_after_double > bundle.condition.oracle_cap_seconds:
        return (
            {
                "case_id": bundle.case_id,
                "condition": bundle.condition.name,
                "replicate": bundle.replicate,
                "status": "ORACLE_TIMEOUT_INCOMPLETE",
                "complete": False,
                "candidate_evaluations": len(candidates),
                "unique_candidate_ids": len(
                    {row["candidate_id"] for row in candidates}
                ),
                "runtime_seconds": elapsed_after_double,
                "wall_seconds_cap": bundle.condition.oracle_cap_seconds,
                "failure_reason": "wall cap reached after complete double enumeration",
                "data_sha256": bundle.data_sha256,
                "profile_metrics": [],
                "oracle_sha256": digest_json(candidates),
            },
            candidates,
        )

    mandatory: dict[int, set[str]] = {}
    for row in candidates:
        margins = [
            abs(
                row["maximum_log_e_double"]
                - math.log(1.0 / PROFILE_PARAMETERS[profile][0])
            )
            for profile in PROFILES
        ]
        if min(margins) <= NEAR_THRESHOLD:
            mandatory.setdefault(row["candidate_id"], set()).add(
                "NEAR_ANY_PROFILE_THRESHOLD"
            )
    controller_ids: set[int] = set()
    witness_ids: set[int] = set()
    elimination_ids: set[int] = set()
    for trace in controller_traces:
        for row in trace["rows"]:
            candidate_id = int(row["candidate_id"])
            controller_ids.add(candidate_id)
            if row["returned_status"] == "ADMISSIBLE":
                witness_ids.add(candidate_id)
            if row["returned_status"] == "REJECTED":
                elimination_ids.add(candidate_id)
    for candidate_id in witness_ids:
        mandatory.setdefault(candidate_id, set()).add("CONTROLLER_WITNESS")
    for candidate_id in elimination_ids:
        mandatory.setdefault(candidate_id, set()).add(
            "CONTROLLER_ORIENTATION_REJECTION"
        )
    far_ids = [
        row["candidate_id"]
        for row in sorted(
            candidates,
            key=lambda item: (
                -min(
                    abs(
                        item["maximum_log_e_double"]
                        - math.log(1.0 / PROFILE_PARAMETERS[profile][0])
                    )
                    for profile in PROFILES
                ),
                item["candidate_id"],
            ),
        )[:FAR_AUDIT_COUNT]
    ]
    for candidate_id in far_ids:
        mandatory.setdefault(candidate_id, set()).add(
            "DETERMINISTIC_FAR_BOUNDARY_AUDIT"
        )

    replay_count = 0
    replay_disagreements = 0

    def replay(candidate_id: int, reason: str) -> None:
        nonlocal replay_count, replay_disagreements
        row = candidates[candidate_id]
        if reason not in row["replay_reasons"]:
            row["replay_reasons"].append(reason)
        if row["high_precision"] is not None:
            return
        candidate = bundle.bank.candidate(candidate_id)
        value = bundle.replay.replay_finite_bank_raw(
            np.asarray(candidate.raw, dtype=float),
            x=np.asarray(candidate.x, dtype=float),
        ).to_json()
        if int(value["decimal_digits"]) != 90:
            raise ArithmeticError("oracle replay precision mismatch")
        row["high_precision"] = value
        replay_count += 1
        if any(
            (row["maximum_log_e_double"] <= math.log(1.0 / params[0]))
            != _hp_survives(value, params[0])
            for params in PROFILE_PARAMETERS.values()
        ):
            replay_disagreements += 1

    for candidate_id in sorted(mandatory):
        for reason in sorted(mandatory[candidate_id]):
            replay(candidate_id, reason)
        if time.monotonic() - started > bundle.condition.oracle_cap_seconds:
            break

    # Replay all three profile endpoints until the final diameters are stable.
    if time.monotonic() - started <= bundle.condition.oracle_cap_seconds:
        for _ in range(42):
            additions: dict[int, set[str]] = {}
            for profile in PROFILES:
                alpha = PROFILE_PARAMETERS[profile][0]
                survivor_ids = {
                    row["candidate_id"]
                    for row in candidates
                    if _candidate_survives(row, alpha)
                }
                _, endpoints = _diameter(bundle, candidates, survivor_ids)
                for endpoint in endpoints:
                    if (
                        endpoint != "PROPOSAL"
                        and candidates[int(endpoint)]["high_precision"] is None
                    ):
                        additions.setdefault(int(endpoint), set()).add(
                            f"{profile}_DIAMETER_ENDPOINT"
                        )
            if not additions:
                break
            for candidate_id, reasons in sorted(additions.items()):
                for reason in sorted(reasons):
                    replay(candidate_id, reason)
        else:
            raise ArithmeticError("oracle endpoint replay did not stabilize")

    runtime = time.monotonic() - started
    complete = runtime <= bundle.condition.oracle_cap_seconds
    profile_metrics: list[dict[str, Any]] = []
    if complete:
        for profile in PROFILES:
            alpha, delta_f_fraction, delta_s_fraction = (
                PROFILE_PARAMETERS[profile]
            )
            survivor_ids = {
                row["candidate_id"]
                for row in candidates
                if _candidate_survives(row, alpha)
            }
            diameter, endpoints = _diameter(
                bundle, candidates, survivor_ids
            )
            for endpoint in endpoints:
                if endpoint != "PROPOSAL":
                    reason = f"{profile}_DIAMETER_ENDPOINT"
                    if reason not in candidates[int(endpoint)]["replay_reasons"]:
                        candidates[int(endpoint)]["replay_reasons"].append(reason)
            truth_radius = _truth_radius(
                bundle, candidates, survivor_ids
            )
            profile_metrics.append(
                {
                    "profile": profile,
                    "alpha": alpha,
                    "delta_f": delta_f_fraction * bundle.d_shell,
                    "delta_s": delta_s_fraction * bundle.d_shell,
                    "survivor_count": len(survivor_ids),
                    "d_bank": diameter,
                    "diameter_fraction": diameter / bundle.d_shell,
                    "diameter_endpoints": endpoints,
                    "oracle_label": _oracle_label(
                        diameter, bundle.d_shell, profile
                    ),
                    "truth_radius": truth_radius,
                    "wrong_fine_truth": (
                        truth_radius > delta_f_fraction * bundle.d_shell
                    ),
                    "wrong_sector_truth": (
                        truth_radius > delta_s_fraction * bundle.d_shell
                    ),
                }
            )
    result_core = {
        "case_id": bundle.case_id,
        "condition": bundle.condition.name,
        "replicate": bundle.replicate,
        "status": "COMPLETE" if complete else "ORACLE_TIMEOUT_INCOMPLETE",
        "complete": complete,
        "candidate_evaluations": len(candidates),
        "unique_candidate_ids": len(
            {row["candidate_id"] for row in candidates}
        ),
        "runtime_seconds": runtime,
        "wall_seconds_cap": bundle.condition.oracle_cap_seconds,
        "resource_hit": not complete,
        "failure_reason": (
            None if complete else "mandatory high-precision audit exceeded wall cap"
        ),
        "data_sha256": bundle.data_sha256,
        "d_shell": bundle.d_shell,
        "replay_count": replay_count,
        "replay_disagreement_count": replay_disagreements,
        "far_audit_candidate_ids": far_ids,
        "controller_candidate_ids": sorted(controller_ids),
        "controller_witness_ids": sorted(witness_ids),
        "controller_elimination_ids": sorted(elimination_ids),
        "profile_metrics": profile_metrics,
    }
    result_core["oracle_sha256"] = digest_json(
        {"result": result_core, "candidates": candidates}
    )
    return result_core, candidates


def audit_controller_against_oracle(
    traces: list[dict[str, Any]],
    budgets: list[dict[str, Any]],
    oracle_result: dict[str, Any],
) -> list[dict[str, Any]]:
    if not oracle_result["complete"]:
        return []
    by_profile = {
        row["profile"]: row for row in oracle_result["profile_metrics"]
    }
    findings: list[dict[str, Any]] = []
    label_for_output = {
        "FINE": "ORACLE_FINE",
        "SECTOR_SAFE": "ORACLE_SECTOR",
        "AMBIGUOUS": "ORACLE_AMBIGUOUS",
    }
    for trace in traces:
        oracle = by_profile[trace["profile"]]
        d_bank = float(oracle["d_bank"])
        states = [trace["initial_state"]]
        states.extend(
            {"lower": row["post_lower"], "upper": row["post_upper"]}
            for row in trace["rows"]
        )
        for index, state in enumerate(states):
            if not (
                float(state["lower"]) <= d_bank + 1.0e-12
                and d_bank <= float(state["upper"]) + 1.0e-12
            ):
                findings.append(
                    {
                        "case_id": trace["case_id"],
                        "profile": trace["profile"],
                        "kind": "BOUND_VIOLATION",
                        "state_index": index,
                        "lower": state["lower"],
                        "d_bank": d_bank,
                        "upper": state["upper"],
                    }
                )
    for row in budgets:
        oracle = by_profile[row["profile"]]
        output = row["output"]
        label = oracle["oracle_label"]
        unsafe = (
            (output == "FINE" and label != "ORACLE_FINE")
            or (output == "SECTOR_SAFE" and label == "ORACLE_AMBIGUOUS")
            or (output == "AMBIGUOUS" and label != "ORACLE_AMBIGUOUS")
        )
        if unsafe:
            findings.append(
                {
                    "case_id": row["case_id"],
                    "profile": row["profile"],
                    "budget_fraction": row["budget_fraction"],
                    "kind": "STRUCTURAL_UNSAFE_OUTPUT",
                    "output": output,
                    "oracle_label": label,
                }
            )
        if (
            float(row["budget_fraction"]) == 1.0
            and label_for_output.get(output) != label
        ):
            findings.append(
                {
                    "case_id": row["case_id"],
                    "profile": row["profile"],
                    "budget_fraction": 1.0,
                    "kind": "EXHAUSTIVE_LABEL_MISMATCH",
                    "output": output,
                    "oracle_label": label,
                }
            )
    return findings
