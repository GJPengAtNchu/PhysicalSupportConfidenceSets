"""Operational R1P.1 proposal facade and G0 safe diagnostic audit.

The operational proposal is imported from the byte-identical inherited module.
Only the non-authorizing proposal audit is implemented here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .config import FROZEN
from .mixture import VariableMixtureCache
from .proposal_3d import (
    AUDIT_SOBOL_SKIP,
    LBFGSB_OPTIONS,
    POWELL_OPTIONS,
    ProposalResult,
    _choose_candidate,
    _distinct_best_starts,
    _sobol_cube,
    construct_proposal,
    frozen_proposal_specification,
)
from .safe_bounds import (
    BOUND_TOLERANCE,
    ConfirmedKernelFailure,
    OptimizerStatus,
    SafeBoundedObjective,
    SafeCounters,
    aggregate_status,
    run_minimize,
)


@dataclass(frozen=True)
class ProposalAudit:
    """Independent deterministic utility audit that cannot alter the proposal."""

    best_x: np.ndarray
    best_log_likelihood: float
    operational_log_likelihood: float
    gap_per_observation: float
    point_count: int
    local_start_count: int
    local_starts_attempted: int
    local_starts_accepted: int
    local_starts_failed: int
    tolerance_clips: int
    hard_out_of_bounds: int
    nonfinite_requests: int
    exact_evaluation_failures: int
    independent_replays: int
    replay_recoveries: int
    confirmed_kernel_failures: int
    status: str
    kernel_error_confirmed: bool
    failure_reason: str | None
    classification: str = "PROPOSAL_AUDIT_DIAGNOSTIC_ONLY"
    alters_operational_proposal: bool = False

    @property
    def legacy_status(self) -> str:
        """Return the R1P.1 audit spelling for provenance comparisons only."""
        return {
            OptimizerStatus.COMPLETE.value: "COMPLETE",
            OptimizerStatus.PARTIAL_FAILURE.value: (
                "PARTIAL_OPTIMIZER_FAILURE"
            ),
            OptimizerStatus.COARSE_ONLY.value: "COARSE_ONLY",
            OptimizerStatus.KERNEL_FAILURE.value: (
                "AUDIT_UNAVAILABLE_KERNEL_ERROR"
            ),
        }[self.status]

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-compatible diagnostic record."""
        record = asdict(self)
        record["best_x"] = self.best_x.tolist()
        record["legacy_status"] = self.legacy_status
        return record


def _negative_likelihood(
    cache: VariableMixtureCache, point: np.ndarray
) -> float:
    value, _, _ = cache.log_likelihood(
        np.asarray(point, dtype=float), derivatives=False
    )
    return -float(value)


def _negative_likelihood_gradient(
    cache: VariableMixtureCache, point: np.ndarray
) -> tuple[float, np.ndarray]:
    value, gradient, _ = cache.log_likelihood(
        np.asarray(point, dtype=float), derivatives=True
    )
    if gradient is None:
        raise ArithmeticError("exact likelihood gradient is unavailable")
    return -float(value), -np.asarray(gradient, dtype=float)


def _audit_objective(
    cache: VariableMixtureCache, counters: SafeCounters
) -> SafeBoundedObjective:
    """Build distinct direct and replay paths over the exact split-A kernel."""

    def value(point: np.ndarray) -> float:
        return _negative_likelihood(cache, point)

    def replay_value(point: np.ndarray) -> float:
        return _negative_likelihood(cache, point)

    def value_gradient(point: np.ndarray) -> tuple[float, np.ndarray]:
        return _negative_likelihood_gradient(cache, point)

    def replay_value_gradient(
        point: np.ndarray,
    ) -> tuple[float, np.ndarray]:
        return _negative_likelihood_gradient(cache, point)

    return SafeBoundedObjective(
        [(-1.0, 1.0)] * 3,
        value,
        value_grad_fn=value_gradient,
        replay_value_fn=replay_value,
        replay_value_grad_fn=replay_value_gradient,
        tolerance=BOUND_TOLERANCE,
        label="proposal_audit_exact_likelihood",
        counters=counters,
    )


def _kernel_audit(
    operational: ProposalResult,
    point_count: int,
    attempted: int,
    accepted: int,
    counters: SafeCounters,
    reason: str,
) -> ProposalAudit:
    """Return a non-authorizing audit record after confirmed replay failure."""
    failed = int(attempted) - int(accepted)
    return ProposalAudit(
        best_x=np.asarray(operational.x, dtype=float).copy(),
        best_log_likelihood=float(operational.log_likelihood),
        operational_log_likelihood=float(operational.log_likelihood),
        gap_per_observation=0.0,
        point_count=int(point_count),
        local_start_count=int(FROZEN.proposal_audit_local_starts),
        local_starts_attempted=int(attempted),
        local_starts_accepted=int(accepted),
        local_starts_failed=max(0, failed),
        tolerance_clips=counters.tolerance_clips,
        hard_out_of_bounds=counters.hard_out_of_bounds,
        nonfinite_requests=counters.nonfinite_requests,
        exact_evaluation_failures=counters.exact_evaluation_failures,
        independent_replays=counters.independent_replays,
        replay_recoveries=counters.replay_recoveries,
        confirmed_kernel_failures=counters.confirmed_kernel_failures,
        status=OptimizerStatus.KERNEL_FAILURE.value,
        kernel_error_confirmed=True,
        failure_reason=str(reason),
    )


def audit_proposal(
    cache_a: VariableMixtureCache,
    operational: ProposalResult,
    sample_size: int,
) -> ProposalAudit:
    """Run the frozen audit through the shared boundary adapter.

    The coarse design, start selection, local methods, and tie rules are
    inherited.  No audit outcome is fed back into ``construct_proposal``.
    """
    counters = SafeCounters()
    objective = _audit_objective(cache_a, counters)
    point_count = int(FROZEN.proposal_audit_points(int(sample_size)))
    points = _sobol_cube(point_count, skip=AUDIT_SOBOL_SKIP)
    values = np.full(point_count, -np.inf, dtype=float)
    try:
        for index, point in enumerate(points):
            values[index] = -float(objective.value(point))
    except ConfirmedKernelFailure as error:
        return _kernel_audit(
            operational,
            point_count,
            attempted=0,
            accepted=0,
            counters=counters,
            reason=str(error),
        )

    finite = np.flatnonzero(np.isfinite(values))
    if not len(finite):
        return _kernel_audit(
            operational,
            point_count,
            attempted=0,
            accepted=0,
            counters=counters,
            reason="no finite deterministic audit coarse likelihood",
        )
    starts = _distinct_best_starts(
        points[finite],
        values[finite],
        int(FROZEN.proposal_audit_local_starts),
    )
    best_index = int(finite[np.argmax(values[finite])])
    candidates: list[tuple[np.ndarray, float]] = [
        (points[best_index].copy(), float(values[best_index]))
    ]
    attempted = 0
    accepted = 0
    failure_reason: str | None = None
    kernel_failure = False

    for start in starts:
        attempted += 1
        local = run_minimize(
            objective,
            np.asarray(start, dtype=float),
            method="L-BFGS-B",
            jac=True,
            options=LBFGSB_OPTIONS,
        )
        if local.status is OptimizerStatus.KERNEL_FAILURE:
            kernel_failure = True
            failure_reason = local.reason
            break
        if local.status is not OptimizerStatus.COMPLETE:
            local = run_minimize(
                objective,
                np.asarray(start, dtype=float),
                method="Powell",
                jac=False,
                options=POWELL_OPTIONS,
            )
        if local.status is OptimizerStatus.KERNEL_FAILURE:
            kernel_failure = True
            failure_reason = local.reason
            break
        if (
            local.status is OptimizerStatus.COMPLETE
            and local.value is not None
        ):
            candidates.append((local.x.copy(), -float(local.value)))
            accepted += 1
        else:
            candidates.append(
                (
                    np.asarray(start, dtype=float).copy(),
                    float(
                        values[
                            int(
                                np.flatnonzero(
                                    np.all(points == start, axis=1)
                                )[0]
                            )
                        ]
                    ),
                )
            )
            failure_reason = local.reason or failure_reason

    if kernel_failure:
        return _kernel_audit(
            operational,
            point_count,
            attempted=attempted,
            accepted=accepted,
            counters=counters,
            reason=failure_reason or "confirmed exact audit kernel failure",
        )

    best_x, best_value = _choose_candidate(candidates)
    failed = attempted - accepted
    status = aggregate_status(
        attempted=attempted,
        accepted=accepted,
        failed=failed,
    )
    gap = max(
        0.0, float(best_value) - float(operational.log_likelihood)
    ) / int(cache_a.size)
    return ProposalAudit(
        best_x=best_x,
        best_log_likelihood=float(best_value),
        operational_log_likelihood=float(operational.log_likelihood),
        gap_per_observation=float(gap),
        point_count=point_count,
        local_start_count=int(FROZEN.proposal_audit_local_starts),
        local_starts_attempted=attempted,
        local_starts_accepted=accepted,
        local_starts_failed=failed,
        tolerance_clips=counters.tolerance_clips,
        hard_out_of_bounds=counters.hard_out_of_bounds,
        nonfinite_requests=counters.nonfinite_requests,
        exact_evaluation_failures=counters.exact_evaluation_failures,
        independent_replays=counters.independent_replays,
        replay_recoveries=counters.replay_recoveries,
        confirmed_kernel_failures=counters.confirmed_kernel_failures,
        status=status.value,
        kernel_error_confirmed=False,
        failure_reason=failure_reason,
    )


__all__ = [
    "ProposalAudit",
    "ProposalResult",
    "audit_proposal",
    "construct_proposal",
    "frozen_proposal_specification",
]
