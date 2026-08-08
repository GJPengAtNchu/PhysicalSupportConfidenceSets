"""Independent logical controller interfaces over one hidden score backend."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import math
from typing import Any

import numpy as np

from ..frozen_policy.ara_controller import (
    AEBFineSeekingController,
    hash_order,
    replay_budget,
    static_farthest_order,
)
from ..frozen_policy.sealed_query import (
    CandidateStatus,
    QueryReceipt,
    SealedQueryCapability,
)

from .constants import BUDGETS, NEAR_THRESHOLD, PROFILE_PARAMETERS
from .science import CaseBundle


def _hp_survives(log_e: tuple[str, ...], alpha: float) -> bool:
    boundary = Decimal(1) / Decimal(repr(float(alpha)))
    threshold = boundary.ln()
    return max(Decimal(value) for value in log_e) <= threshold


@dataclass
class ScoreRecord:
    candidate_id: int
    log_e: tuple[float, ...]
    maximum_log_e: float
    maximum_checkpoint: int


class HiddenScoreBackend:
    """Alpha-independent numerical cache that exposes no table to policy code."""

    def __init__(self, bundle: CaseBundle):
        self.bundle = bundle
        self._double: dict[int, ScoreRecord] = {}
        self._hp: dict[int, dict[str, Any]] = {}
        self._hp_reasons: dict[int, set[str]] = {}
        self.double_evaluations = 0
        self.double_cache_hits = 0
        self.hp_evaluations = 0
        self.hp_cache_hits = 0

    def score(self, candidate_id: int) -> tuple[ScoreRecord, bool]:
        cached = self._double.get(candidate_id)
        if cached is not None:
            self.double_cache_hits += 1
            return cached, True
        candidate = self.bundle.bank.candidate(candidate_id)
        values, gradient, hessian = (
            self.bundle.eprocess.evaluate_finite_bank_raw(
                np.asarray(candidate.raw, dtype=float), derivatives=False
            )
        )
        if gradient is not None or hessian is not None:
            raise ArithmeticError("derivative-free score returned derivatives")
        array = np.asarray(values, dtype=float)
        checkpoints = np.asarray(self.bundle.eprocess.checkpoints, dtype=int)
        if array.shape != checkpoints.shape or not np.all(np.isfinite(array)):
            raise ArithmeticError("invalid candidate checkpoint score")
        maximum_index = int(np.argmax(array))
        record = ScoreRecord(
            candidate_id=candidate_id,
            log_e=tuple(float(value) for value in array),
            maximum_log_e=float(array[maximum_index]),
            maximum_checkpoint=int(checkpoints[maximum_index]),
        )
        self._double[candidate_id] = record
        self.double_evaluations += 1
        return record, False

    def high_precision(
        self, candidate_id: int, reason: str
    ) -> tuple[dict[str, Any], bool]:
        self._hp_reasons.setdefault(candidate_id, set()).add(reason)
        cached = self._hp.get(candidate_id)
        if cached is not None:
            self.hp_cache_hits += 1
            return cached, True
        candidate = self.bundle.bank.candidate(candidate_id)
        replay = self.bundle.replay.replay_finite_bank_raw(
            np.asarray(candidate.raw, dtype=float),
            x=np.asarray(candidate.x, dtype=float),
        )
        record = replay.to_json()
        if int(record["decimal_digits"]) != 90:
            raise ArithmeticError("high-precision replay is not 90 decimal")
        if len(record["log_e"]) != len(self.bundle.eprocess.checkpoints):
            raise ArithmeticError("high-precision replay checkpoint mismatch")
        self._hp[candidate_id] = record
        self.hp_evaluations += 1
        return record, False

    def hp_reason_map(self) -> dict[str, list[str]]:
        return {
            str(key): sorted(value)
            for key, value in sorted(self._hp_reasons.items())
        }

    def double_records(self) -> dict[int, ScoreRecord]:
        return dict(self._double)

    def hp_records(self) -> dict[int, dict[str, Any]]:
        return dict(self._hp)


class LogicalProfileBackend:
    """One cold logical query history backed by a shared numerical cache."""

    def __init__(self, hidden: HiddenScoreBackend, profile: str):
        self.hidden = hidden
        self.profile = profile
        self.alpha = PROFILE_PARAMETERS[profile][0]
        self.allowed = frozenset(
            str(candidate.candidate_id) for candidate in hidden.bundle.bank
        )
        self.queried: set[str] = set()
        self.events: list[dict[str, Any]] = []
        self.counter = 0
        self._capability = SealedQueryCapability(self._query_one)

    def capability(self) -> SealedQueryCapability:
        return self._capability

    def _query_one(self, candidate_id: str) -> QueryReceipt:
        if candidate_id not in self.allowed:
            raise KeyError(candidate_id)
        if candidate_id in self.queried:
            raise RuntimeError("duplicate logical query")
        self.queried.add(candidate_id)
        self.counter += 1
        value = int(candidate_id)
        score, double_hit = self.hidden.score(value)
        threshold = math.log(1.0 / self.alpha)
        margin = score.maximum_log_e - threshold
        provisional = margin <= 0.0
        reasons: list[str] = []
        if provisional:
            reasons.append("PROVISIONAL_SURVIVOR")
        if abs(margin) <= NEAR_THRESHOLD:
            reasons.append("NEAR_THRESHOLD")
        # The frozen controller completes an orientation action only after a
        # survivor or after all nuisance candidates reject.  Replaying every
        # provisional rejection is a conservative strict implementation of
        # the required pre-elimination replay and permits no stale rejection
        # to enter controller state.
        if not provisional:
            reasons.append("PRE_ELIMINATION_REJECTION")
        hp_record: dict[str, Any] | None = None
        hp_hit = False
        if reasons:
            hp_record, hp_hit = self.hidden.high_precision(value, reasons[0])
            for reason in reasons[1:]:
                self.hidden._hp_reasons.setdefault(value, set()).add(reason)
            admissible = _hp_survives(
                tuple(str(item) for item in hp_record["log_e"]), self.alpha
            )
        else:
            admissible = provisional
        status = (
            CandidateStatus.ADMISSIBLE
            if admissible
            else CandidateStatus.REJECTED
        )
        self.events.append(
            {
                "query_number": self.counter,
                "candidate_id": candidate_id,
                "profile": self.profile,
                "maximum_log_e_double": score.maximum_log_e,
                "threshold": threshold,
                "margin_double": margin,
                "double_cache_hit": double_hit,
                "replay_required": bool(reasons),
                "replay_reasons": reasons,
                "high_precision_cache_hit": hp_hit if reasons else False,
                "returned_status": status.value,
                "double_high_precision_disagreement": (
                    bool(admissible) != bool(provisional)
                ),
            }
        )
        return QueryReceipt(self.counter, candidate_id, status)


def run_profile(
    bundle: CaseBundle,
    hidden: HiddenScoreBackend,
    profile: str,
    *,
    orientation_selector=None,
) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
    logical = LogicalProfileBackend(hidden, profile)
    controller = AEBFineSeekingController(bundle.manifest, profile)
    trace = controller.run_maximal(
        logical.capability(), orientation_selector=orientation_selector
    )
    seal = trace.seal_trace()
    budgets = [replay_budget(trace, value) for value in BUDGETS]
    for record in budgets:
        record["condition"] = bundle.condition.name
        record["replicate"] = bundle.replicate
    if len(trace.rows) != len(logical.events):
        raise AssertionError("trace and logical event counts differ")
    for row, event in zip(trace.rows, logical.events):
        if row["candidate_id"] != event["candidate_id"]:
            raise AssertionError("trace and logical query order differ")
        row.update(
            {
                key: value
                for key, value in event.items()
                if key not in {"query_number", "candidate_id", "profile"}
            }
        )
    trace_record = {
        "case_id": bundle.case_id,
        "condition": bundle.condition.name,
        "replicate": bundle.replicate,
        "profile": profile,
        "bank_size": trace.bank_size,
        "d_shell": trace.d_shell,
        "delta_f": trace.delta_f,
        "delta_s": trace.delta_s,
        "initial_state": trace.initial_state,
        "rows": trace.rows,
        "terminal_output": trace.terminal_output,
        "terminal_query_count": trace.terminal_query_count,
        "completed_actions": trace.completed_actions,
        "provisional_sector_query": trace.provisional_sector_query,
        "trace_sha256": seal.trace_sha256,
        "sealed": True,
    }
    return trace, budgets, [trace_record]


def baseline_selector(name: str, controller: AEBFineSeekingController):
    if name == "STATIC_FARTHEST":
        from frozen_policy.ara_controller import fixed_order_selector

        return fixed_order_selector(static_farthest_order(controller))
    if name == "CANONICAL_GROUP_ORDER":
        from frozen_policy.ara_controller import fixed_order_selector

        return fixed_order_selector(tuple(group.index for group in controller.groups))
    if name == "RANDOM_HASH_ORDER":
        from frozen_policy.ara_controller import fixed_order_selector

        order = hash_order(
            controller.case_id,
            controller.profile,
            (group.index for group in controller.groups),
        )
        return fixed_order_selector(order)
    return None
