"""Deterministic split-A proposal with one safe bounded-optimizer interface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from typing import Any

import numpy as np
from scipy.stats import qmc

from .config import FROZEN
from .mixture import VariableMixtureCache
from .safe_bounds import (
    BOUND_TOLERANCE,
    ConfirmedKernelFailure,
    OptimizerStatus,
    SafeBoundedObjective,
    SafeCounters,
    run_minimize,
)
from .transforms import normalized_to_raw


PROPOSAL_SOBOL_SKIP = 0
AUDIT_SOBOL_SKIP = 1024
OPTIMIZER_TIE_TOLERANCE = 1.0e-10
LBFGSB_OPTIONS = {"maxiter": 350, "ftol": 1.0e-12, "gtol": 1.0e-8}
POWELL_OPTIONS = {"maxiter": 500, "ftol": 1.0e-12, "xtol": 1.0e-10}


@dataclass(frozen=True)
class ProposalResult:
    """Operational proposal fixed before split B or any bank is inspected."""

    x: np.ndarray
    raw: tuple[float, float, float]
    log_likelihood: float
    status: str
    fallback_count: int
    failed_start_count: int
    coarse_best_log_likelihood: float
    local_starts_attempted: int
    local_starts_accepted: int
    lbfgsb_attempted: int
    lbfgsb_accepted: int
    powell_attempted: int
    powell_accepted: int
    tolerance_clips: int
    hard_out_of_bound_requests: int
    nonfinite_requests: int
    malformed_requests: int
    exact_evaluation_failures: int
    independent_replays: int
    replay_recoveries: int
    confirmed_kernel_failures: int
    coarse_fallback_used: bool

    def to_json(self) -> dict[str, Any]:
        record = asdict(self)
        record["x"] = self.x.tolist()
        record["raw"] = list(self.raw)
        return record


def _sobol_cube(count: int, *, skip: int) -> np.ndarray:
    """Return a deterministic unscrambled Sobol block in ``[-1,1]^3``."""
    engine = qmc.Sobol(d=3, scramble=False)
    if skip:
        engine.fast_forward(int(skip))
    with np.errstate(all="ignore"):
        points = engine.random(int(count))
    return 2.0 * points - 1.0


def _center_corners_faces() -> np.ndarray:
    center = np.zeros((1, 3), dtype=float)
    corners = np.asarray(list(product((-1.0, 1.0), repeat=3)), dtype=float)
    faces: list[np.ndarray] = []
    for dimension in range(3):
        for side in (-1.0, 1.0):
            point = np.zeros(3, dtype=float)
            point[dimension] = side
            faces.append(point)
    return np.vstack((center, corners, np.asarray(faces)))


def proposal_coarse_points() -> np.ndarray:
    """Return the inherited exact operational proposal point set."""
    return np.vstack(
        (
            _sobol_cube(
                FROZEN.proposal_sobol_points, skip=PROPOSAL_SOBOL_SKIP
            ),
            _center_corners_faces(),
        )
    )


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


def _operational_objective(
    cache: VariableMixtureCache,
    counters: SafeCounters,
) -> SafeBoundedObjective:
    """Build direct and independent replay closures over the strict kernel."""

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
        label="operational_proposal_exact_likelihood",
        counters=counters,
    )


def _distinct_best_starts(
    points: np.ndarray, values: np.ndarray, count: int
) -> np.ndarray:
    """Select likelihood-ranked distinct starts with inherited tie rules."""
    ranked = sorted(
        range(len(points)),
        key=lambda index: (
            -float(values[index]),
            float(np.linalg.norm(points[index])),
            tuple(float(value) for value in points[index]),
        ),
    )
    selected: list[np.ndarray] = []
    for index in ranked:
        point = points[index]
        if not any(np.array_equal(point, prior) for prior in selected):
            selected.append(point.copy())
        if len(selected) == int(count):
            break
    return np.asarray(selected)


def _choose_candidate(
    candidates: list[tuple[np.ndarray, float]],
) -> tuple[np.ndarray, float]:
    """Choose the likelihood maximum with inherited deterministic tie breaks."""
    best_value = max(value for _, value in candidates)
    tied = [
        (point, value)
        for point, value in candidates
        if best_value - value <= OPTIMIZER_TIE_TOLERANCE
    ]
    tied.sort(
        key=lambda item: (
            float(np.linalg.norm(item[0])),
            tuple(float(value) for value in item[0]),
        )
    )
    return tied[0][0].copy(), float(tied[0][1])


def _exact_coarse_candidates(
    objective: SafeBoundedObjective,
    points: np.ndarray,
) -> tuple[np.ndarray, list[tuple[np.ndarray, float]]]:
    values = np.empty(len(points), dtype=float)
    candidates: list[tuple[np.ndarray, float]] = []
    for index, point in enumerate(points):
        exact = objective.exact_candidate(point)
        if exact.status is OptimizerStatus.KERNEL_FAILURE:
            raise ConfirmedKernelFailure(
                objective.label,
                np.asarray(point, dtype=float),
                exact.reason or "exact coarse evaluation failed",
                exact.reason or "independent exact coarse replay failed",
            )
        if not exact.accepted or exact.value is None:
            raise ArithmeticError("declared in-shell coarse point was rejected")
        likelihood = -float(exact.value)
        values[index] = likelihood
        candidates.append((exact.x.copy(), likelihood))
    return values, candidates


def construct_proposal(cache_a: VariableMixtureCache) -> ProposalResult:
    """Construct the repaired split-A proposal through the shared adapter."""
    counters = SafeCounters()
    objective = _operational_objective(cache_a, counters)
    coarse = proposal_coarse_points()
    values, coarse_candidates = _exact_coarse_candidates(objective, coarse)
    starts = _distinct_best_starts(
        coarse, values, FROZEN.proposal_local_starts
    )
    best_coarse_index = int(np.argmax(values))
    best_coarse = [coarse_candidates[best_coarse_index]]

    lbfgsb_candidates: list[tuple[np.ndarray, float]] = []
    powell_candidates: list[tuple[np.ndarray, float]] = []
    lbfgsb_attempted = 0
    powell_attempted = 0
    failed_starts = 0
    for start in starts:
        lbfgsb_attempted += 1
        lbfgsb = run_minimize(
            objective,
            np.asarray(start, dtype=float),
            method="L-BFGS-B",
            jac=True,
            options=LBFGSB_OPTIONS,
        )
        if lbfgsb.status is OptimizerStatus.KERNEL_FAILURE:
            raise ConfirmedKernelFailure(
                objective.label,
                np.asarray(start, dtype=float),
                lbfgsb.reason or "L-BFGS-B exact kernel failure",
                lbfgsb.reason or "L-BFGS-B independent replay failure",
            )
        if (
            lbfgsb.status is OptimizerStatus.COMPLETE
            and lbfgsb.value is not None
        ):
            lbfgsb_candidates.append(
                (lbfgsb.x.copy(), -float(lbfgsb.value))
            )
            continue

        powell_attempted += 1
        powell = run_minimize(
            objective,
            np.asarray(start, dtype=float),
            method="Powell",
            jac=False,
            options=POWELL_OPTIONS,
        )
        if powell.status is OptimizerStatus.KERNEL_FAILURE:
            raise ConfirmedKernelFailure(
                objective.label,
                np.asarray(start, dtype=float),
                powell.reason or "Powell exact kernel failure",
                powell.reason or "Powell independent replay failure",
            )
        if (
            powell.status is OptimizerStatus.COMPLETE
            and powell.value is not None
        ):
            powell_candidates.append(
                (powell.x.copy(), -float(powell.value))
            )
        else:
            failed_starts += 1

    if lbfgsb_candidates:
        selected_pool = lbfgsb_candidates
        coarse_fallback = False
    elif powell_candidates:
        selected_pool = powell_candidates
        coarse_fallback = False
    else:
        selected_pool = best_coarse
        coarse_fallback = True

    point, likelihood = _choose_candidate(selected_pool)
    if not np.isfinite(likelihood):
        raise ArithmeticError("proposal hierarchy produced nonfinite likelihood")
    local_accepted = len(lbfgsb_candidates) + len(powell_candidates)
    if coarse_fallback:
        status = "COARSE_FALLBACK"
    elif (
        failed_starts
        or powell_attempted
        or local_accepted != len(starts)
    ):
        status = "LOCAL_PARTIAL_FAILURE"
    else:
        status = "LOCAL_COMPLETE"
    raw = normalized_to_raw(point)
    return ProposalResult(
        x=point,
        raw=(float(raw[0]), float(raw[1]), float(raw[2])),
        log_likelihood=float(likelihood),
        status=status,
        fallback_count=int(powell_attempted),
        failed_start_count=int(failed_starts),
        coarse_best_log_likelihood=float(values[best_coarse_index]),
        local_starts_attempted=len(starts),
        local_starts_accepted=local_accepted,
        lbfgsb_attempted=lbfgsb_attempted,
        lbfgsb_accepted=len(lbfgsb_candidates),
        powell_attempted=powell_attempted,
        powell_accepted=len(powell_candidates),
        tolerance_clips=counters.tolerance_clips,
        hard_out_of_bound_requests=counters.hard_out_of_bounds,
        nonfinite_requests=counters.nonfinite_requests,
        malformed_requests=counters.malformed_requests,
        exact_evaluation_failures=counters.exact_evaluation_failures,
        independent_replays=counters.independent_replays,
        replay_recoveries=counters.replay_recoveries,
        confirmed_kernel_failures=counters.confirmed_kernel_failures,
        coarse_fallback_used=coarse_fallback,
    )


def frozen_proposal_specification() -> dict[str, Any]:
    return {
        "coarse": {
            "sobol_unscrambled": True,
            "sobol_points": FROZEN.proposal_sobol_points,
            "sobol_skip": PROPOSAL_SOBOL_SKIP,
            "center": 1,
            "corners": 8,
            "face_centers": 6,
        },
        "local_starts": FROZEN.proposal_local_starts,
        "shared_adapter": "SafeBoundedObjective",
        "bound_tolerance": BOUND_TOLERANCE,
        "fallback_hierarchy": [
            "best_valid_lbfgsb",
            "best_valid_safe_powell",
            "best_exact_coarse",
        ],
        "terminal_candidate_exact_replay": True,
        "strict_transform_unchanged": True,
        "tie_break": ["distance_to_center", "x_phi", "x_p", "x_nu"],
        "audit_sobol_skip": AUDIT_SOBOL_SKIP,
        "audit_local_starts": FROZEN.proposal_audit_local_starts,
        "audit_alters_proposal": False,
    }
