"""Frozen split-B likelihood-ratio e-process over normalized R1 coordinates."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import FROZEN
from .mixture import VariableMixtureCache


def frozen_checkpoints(evaluation_size: int) -> np.ndarray:
    """Return powers of two from 128 plus the final held-out prefix."""
    size = int(evaluation_size)
    if size < FROZEN.checkpoint_minimum:
        return np.asarray([size], dtype=int)
    checkpoints: list[int] = []
    value = FROZEN.checkpoint_minimum
    while value <= size:
        checkpoints.append(value)
        value *= 2
    if checkpoints[-1] != size:
        checkpoints.append(size)
    return np.asarray(checkpoints, dtype=int)


@dataclass(frozen=True)
class EProcess3D:
    """Checkpoint log e-values with one split-A numerator candidate."""

    cache_b: VariableMixtureCache
    proposal_x: np.ndarray
    checkpoints: np.ndarray
    numerator_loglikelihood: np.ndarray

    @classmethod
    def from_evaluation(
        cls, cache_b: VariableMixtureCache, proposal_x: np.ndarray
    ) -> "EProcess3D":
        """Freeze numerator prefixes using the supplied split-B order."""
        point = np.asarray(proposal_x, dtype=float)
        checkpoints = frozen_checkpoints(cache_b.size)
        numerator, _, _ = cache_b.log_likelihood_checkpoints(
            point, checkpoints, derivatives=False
        )
        return cls(
            cache_b=cache_b,
            proposal_x=point.copy(),
            checkpoints=checkpoints,
            numerator_loglikelihood=numerator,
        )

    def evaluate(
        self, x: np.ndarray, *, derivatives: bool = False
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
        """Return checkpoint log e-values and normalized derivatives."""
        denominator, gradient, hessian = (
            self.cache_b.log_likelihood_checkpoints(
                np.asarray(x, dtype=float),
                self.checkpoints,
                derivatives=derivatives,
            )
        )
        log_e = self.numerator_loglikelihood - denominator
        if not derivatives:
            return log_e, None, None
        assert gradient is not None and hessian is not None
        return log_e, -gradient, -hessian

    def rejection_score(self, x: np.ndarray) -> float:
        """Return `max_k(log E_k-b_D)`; nonpositive candidates survive."""
        log_e, _, _ = self.evaluate(np.asarray(x, dtype=float))
        return float(np.max(log_e - FROZEN.threshold))

    def survives(self, x: np.ndarray) -> bool:
        """Return whether a point survives every checkpoint."""
        return bool(self.rejection_score(np.asarray(x, dtype=float)) <= 0.0)
