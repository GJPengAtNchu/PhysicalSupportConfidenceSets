"""Shared fail-closed boundary adapter for every bounded optimizer.

The exact statistical kernels keep their strict closed-domain checks.  This
module handles optimizer trial-point behaviour before any such kernel is
called.  It does not enlarge a bound, alter an objective, or authorize a
scientific conclusion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable, Sequence

import numpy as np
from scipy.optimize import minimize, minimize_scalar


BOUND_TOLERANCE = 1.0e-10

ValueFunction = Callable[[np.ndarray], float]
ValueGradientFunction = Callable[
    [np.ndarray], tuple[float, np.ndarray]
]


class OptimizerStatus(str, Enum):
    """Frozen status vocabulary for every repaired or new local optimizer."""

    COMPLETE = "COMPLETE"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    COARSE_ONLY = "COARSE_ONLY"
    KERNEL_FAILURE = "KERNEL_FAILURE"


class ConfirmedKernelFailure(RuntimeError):
    """An exact in-shell failure repeated under an independent direct replay."""

    def __init__(
        self,
        label: str,
        point: np.ndarray,
        primary_reason: str,
        replay_reason: str,
    ) -> None:
        self.label = str(label)
        self.point = np.asarray(point, dtype=float).copy()
        self.primary_reason = str(primary_reason)
        self.replay_reason = str(replay_reason)
        super().__init__(
            f"{self.label}: confirmed exact in-shell failure at "
            f"{self.point.tolist()}: primary={self.primary_reason}; "
            f"replay={self.replay_reason}"
        )


@dataclass
class SafeCounters:
    """Deterministic boundary and independent-replay diagnostics."""

    requests: int = 0
    final_candidate_requests: int = 0
    nonfinite_requests: int = 0
    hard_out_of_bounds: int = 0
    malformed_requests: int = 0
    tolerance_clips: int = 0
    tolerance_clipped_coordinates: int = 0
    exact_evaluation_failures: int = 0
    independent_replays: int = 0
    replay_recoveries: int = 0
    confirmed_kernel_failures: int = 0
    rejected_final_nonfinite: int = 0
    rejected_final_out_of_bounds: int = 0
    accepted_final_candidates: int = 0

    def to_json(self) -> dict[str, int]:
        """Return a JSON-compatible counter snapshot."""
        return {key: int(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class SafeCandidate:
    """An exact terminal-candidate validation result."""

    accepted: bool
    x: np.ndarray
    value: float | None
    status: OptimizerStatus | None
    recovered_by_replay: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class LocalOptimizerResult:
    """One bounded local-optimizer attempt after exact terminal validation."""

    x: np.ndarray
    value: float | None
    status: OptimizerStatus
    method: str
    optimizer_success: bool
    recovered_by_replay: bool = False
    reason: str | None = None


def aggregate_status(
    *,
    attempted: int,
    accepted: int,
    failed: int,
    kernel_failure: bool = False,
) -> OptimizerStatus:
    """Aggregate deterministic local-work counts into the frozen vocabulary."""
    if kernel_failure:
        return OptimizerStatus.KERNEL_FAILURE
    if int(accepted) == 0:
        return OptimizerStatus.COARSE_ONLY
    if int(failed) or int(accepted) != int(attempted):
        return OptimizerStatus.PARTIAL_FAILURE
    return OptimizerStatus.COMPLETE


class SafeBoundedObjective:
    """Protect a strict exact objective from bounded-optimizer trial behaviour.

    ``replay_value_fn`` and ``replay_value_grad_fn`` must be direct evaluation
    paths.  In particular, callers with a candidate-score cache must bypass
    that cache in the replay closures.
    """

    def __init__(
        self,
        bounds: Sequence[tuple[float, float]],
        value_fn: ValueFunction,
        *,
        value_grad_fn: ValueGradientFunction | None = None,
        replay_value_fn: ValueFunction,
        replay_value_grad_fn: ValueGradientFunction | None = None,
        tolerance: float = BOUND_TOLERANCE,
        label: str = "bounded_objective",
        counters: SafeCounters | None = None,
    ) -> None:
        box = np.asarray(tuple(bounds), dtype=float)
        if (
            box.ndim != 2
            or box.shape[1:] != (2,)
            or not len(box)
            or not np.all(np.isfinite(box))
            or np.any(box[:, 0] > box[:, 1])
        ):
            raise ValueError("bounds must be finite ordered (lower, upper) pairs")
        if not np.isfinite(tolerance) or float(tolerance) < 0.0:
            raise ValueError("boundary tolerance must be finite and nonnegative")
        if value_grad_fn is not None and replay_value_grad_fn is None:
            raise ValueError(
                "a gradient objective requires an independent gradient replay"
            )
        self._bounds = box
        self._value_fn = value_fn
        self._value_grad_fn = value_grad_fn
        self._replay_value_fn = replay_value_fn
        self._replay_value_grad_fn = replay_value_grad_fn
        self.tolerance = float(tolerance)
        self.label = str(label)
        self.counters = counters if counters is not None else SafeCounters()

    @property
    def dimension(self) -> int:
        """Return the optimizer-coordinate dimension."""
        return int(self._bounds.shape[0])

    @property
    def bounds(self) -> tuple[tuple[float, float], ...]:
        """Return immutable SciPy-compatible closed bounds."""
        return tuple(
            (float(lower), float(upper)) for lower, upper in self._bounds
        )

    def _sanitize(
        self, x: np.ndarray | Sequence[float] | float, *, final: bool
    ) -> tuple[np.ndarray | None, str | None]:
        point = np.asarray(x, dtype=float)
        if point.shape == () and self.dimension == 1:
            point = point.reshape(1)
        if point.shape != (self.dimension,):
            self.counters.malformed_requests += 1
            if final:
                self.counters.rejected_final_out_of_bounds += 1
            return None, "malformed optimizer coordinate"
        if not np.all(np.isfinite(point)):
            self.counters.nonfinite_requests += 1
            if final:
                self.counters.rejected_final_nonfinite += 1
            return None, "nonfinite optimizer coordinate"
        lower = self._bounds[:, 0]
        upper = self._bounds[:, 1]
        if np.any(point < lower - self.tolerance) or np.any(
            point > upper + self.tolerance
        ):
            self.counters.hard_out_of_bounds += 1
            if final:
                self.counters.rejected_final_out_of_bounds += 1
            return None, "optimizer coordinate materially outside bounds"
        safe = np.clip(point, lower, upper)
        clipped = safe != point
        if np.any(clipped):
            self.counters.tolerance_clips += 1
            self.counters.tolerance_clipped_coordinates += int(
                np.count_nonzero(clipped)
            )
        return safe, None

    @staticmethod
    def _finite_value(result: Any) -> tuple[float, np.ndarray | None]:
        value = float(result)
        if not np.isfinite(value):
            raise FloatingPointError("exact objective returned a nonfinite value")
        return value, None

    def _finite_value_gradient(
        self, result: Any
    ) -> tuple[float, np.ndarray]:
        value_raw, gradient_raw = result
        value = float(value_raw)
        gradient = np.asarray(gradient_raw, dtype=float)
        if not np.isfinite(value):
            raise FloatingPointError("exact objective returned a nonfinite value")
        if gradient.shape != (self.dimension,):
            raise ValueError("exact objective returned a malformed gradient")
        if not np.all(np.isfinite(gradient)):
            raise FloatingPointError(
                "exact objective returned a nonfinite gradient"
            )
        return value, gradient

    def _evaluate_value(
        self, point: np.ndarray
    ) -> tuple[float, bool]:
        try:
            value, _ = self._finite_value(self._value_fn(point.copy()))
            return value, False
        except Exception as primary_error:
            self.counters.exact_evaluation_failures += 1
            self.counters.independent_replays += 1
            try:
                value, _ = self._finite_value(
                    self._replay_value_fn(point.copy())
                )
            except Exception as replay_error:
                self.counters.exact_evaluation_failures += 1
                self.counters.confirmed_kernel_failures += 1
                raise ConfirmedKernelFailure(
                    self.label,
                    point,
                    repr(primary_error),
                    repr(replay_error),
                ) from replay_error
            self.counters.replay_recoveries += 1
            return value, True

    def _evaluate_value_gradient(
        self, point: np.ndarray
    ) -> tuple[float, np.ndarray, bool]:
        if self._value_grad_fn is None or self._replay_value_grad_fn is None:
            raise TypeError(f"{self.label} has no gradient evaluation path")
        try:
            value, gradient = self._finite_value_gradient(
                self._value_grad_fn(point.copy())
            )
            return value, gradient, False
        except Exception as primary_error:
            self.counters.exact_evaluation_failures += 1
            self.counters.independent_replays += 1
            try:
                value, gradient = self._finite_value_gradient(
                    self._replay_value_grad_fn(point.copy())
                )
            except Exception as replay_error:
                self.counters.exact_evaluation_failures += 1
                self.counters.confirmed_kernel_failures += 1
                raise ConfirmedKernelFailure(
                    self.label,
                    point,
                    repr(primary_error),
                    repr(replay_error),
                ) from replay_error
            self.counters.replay_recoveries += 1
            return value, gradient, True

    def value(self, x: np.ndarray | Sequence[float] | float) -> float:
        """Return a safe scalar objective value for SciPy."""
        self.counters.requests += 1
        safe, _ = self._sanitize(x, final=False)
        if safe is None:
            return np.inf
        value, _ = self._evaluate_value(safe)
        return float(value)

    def value_grad(
        self, x: np.ndarray | Sequence[float] | float
    ) -> tuple[float, np.ndarray]:
        """Return a safe value/gradient pair for a jacobian-aware optimizer."""
        self.counters.requests += 1
        safe, _ = self._sanitize(x, final=False)
        if safe is None:
            return np.inf, np.zeros(self.dimension, dtype=float)
        value, gradient, _ = self._evaluate_value_gradient(safe)
        return float(value), gradient

    def exact_candidate(
        self, x: np.ndarray | Sequence[float] | float
    ) -> SafeCandidate:
        """Validate and independently exact-evaluate one terminal candidate."""
        self.counters.final_candidate_requests += 1
        safe, reason = self._sanitize(x, final=True)
        if safe is None:
            point = np.asarray(x, dtype=float)
            return SafeCandidate(
                accepted=False,
                x=point.copy(),
                value=None,
                status=None,
                reason=reason,
            )
        try:
            value, recovered = self._evaluate_value(safe)
        except ConfirmedKernelFailure as error:
            return SafeCandidate(
                accepted=False,
                x=safe.copy(),
                value=None,
                status=OptimizerStatus.KERNEL_FAILURE,
                reason=str(error),
            )
        self.counters.accepted_final_candidates += 1
        return SafeCandidate(
            accepted=True,
            x=safe.copy(),
            value=float(value),
            status=None,
            recovered_by_replay=bool(recovered),
        )


def run_minimize(
    objective: SafeBoundedObjective,
    start: np.ndarray,
    *,
    method: str,
    jac: bool,
    options: dict[str, Any],
    terminal_exact: SafeBoundedObjective | None = None,
) -> LocalOptimizerResult:
    """Run one SciPy minimization and require a safe exact terminal replay."""
    initial = np.asarray(start, dtype=float).copy()
    terminal = terminal_exact if terminal_exact is not None else objective
    try:
        result = minimize(
            objective.value_grad if jac else objective.value,
            initial,
            method=str(method),
            jac=True if jac else None,
            bounds=objective.bounds,
            options=dict(options),
        )
    except ConfirmedKernelFailure as error:
        return LocalOptimizerResult(
            x=initial,
            value=None,
            status=OptimizerStatus.KERNEL_FAILURE,
            method=str(method),
            optimizer_success=False,
            reason=str(error),
        )
    except Exception as error:
        return LocalOptimizerResult(
            x=initial,
            value=None,
            status=OptimizerStatus.COARSE_ONLY,
            method=str(method),
            optimizer_success=False,
            reason=repr(error),
        )
    if not bool(result.success):
        return LocalOptimizerResult(
            x=initial,
            value=None,
            status=OptimizerStatus.COARSE_ONLY,
            method=str(method),
            optimizer_success=False,
            reason=str(getattr(result, "message", "optimizer failed")),
        )
    candidate = terminal.exact_candidate(np.asarray(result.x, dtype=float))
    if candidate.status is OptimizerStatus.KERNEL_FAILURE:
        return LocalOptimizerResult(
            x=initial,
            value=None,
            status=OptimizerStatus.KERNEL_FAILURE,
            method=str(method),
            optimizer_success=True,
            reason=candidate.reason,
        )
    if not candidate.accepted:
        return LocalOptimizerResult(
            x=initial,
            value=None,
            status=OptimizerStatus.COARSE_ONLY,
            method=str(method),
            optimizer_success=True,
            reason=candidate.reason,
        )
    return LocalOptimizerResult(
        x=candidate.x.copy(),
        value=float(candidate.value),
        status=OptimizerStatus.COMPLETE,
        method=str(method),
        optimizer_success=True,
        recovered_by_replay=candidate.recovered_by_replay,
    )


def run_minimize_scalar(
    objective: SafeBoundedObjective,
    *,
    options: dict[str, Any],
    terminal_exact: SafeBoundedObjective | None = None,
) -> LocalOptimizerResult:
    """Run one one-dimensional bounded refinement through the same adapter."""
    if objective.dimension != 1:
        raise ValueError("scalar refinement requires one-dimensional bounds")
    terminal = terminal_exact if terminal_exact is not None else objective
    midpoint = np.asarray(
        [0.5 * sum(objective.bounds[0])], dtype=float
    )
    try:
        result = minimize_scalar(
            lambda value: objective.value(float(value)),
            bounds=objective.bounds[0],
            method="bounded",
            options=dict(options),
        )
    except ConfirmedKernelFailure as error:
        return LocalOptimizerResult(
            x=midpoint,
            value=None,
            status=OptimizerStatus.KERNEL_FAILURE,
            method="bounded",
            optimizer_success=False,
            reason=str(error),
        )
    except Exception as error:
        return LocalOptimizerResult(
            x=midpoint,
            value=None,
            status=OptimizerStatus.COARSE_ONLY,
            method="bounded",
            optimizer_success=False,
            reason=repr(error),
        )
    if not bool(result.success):
        return LocalOptimizerResult(
            x=midpoint,
            value=None,
            status=OptimizerStatus.COARSE_ONLY,
            method="bounded",
            optimizer_success=False,
            reason=str(getattr(result, "message", "optimizer failed")),
        )
    candidate = terminal.exact_candidate(np.asarray([result.x], dtype=float))
    if candidate.status is OptimizerStatus.KERNEL_FAILURE:
        return LocalOptimizerResult(
            x=midpoint,
            value=None,
            status=OptimizerStatus.KERNEL_FAILURE,
            method="bounded",
            optimizer_success=True,
            reason=candidate.reason,
        )
    if not candidate.accepted:
        return LocalOptimizerResult(
            x=midpoint,
            value=None,
            status=OptimizerStatus.COARSE_ONLY,
            method="bounded",
            optimizer_success=True,
            reason=candidate.reason,
        )
    return LocalOptimizerResult(
        x=candidate.x.copy(),
        value=float(candidate.value),
        status=OptimizerStatus.COMPLETE,
        method="bounded",
        optimizer_success=True,
        recovered_by_replay=candidate.recovered_by_replay,
    )
