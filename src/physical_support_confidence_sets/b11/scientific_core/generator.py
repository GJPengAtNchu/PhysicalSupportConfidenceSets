"""Frozen R1 Bernoulli-Gaussian generator and split isolation."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .config import FROZEN
from .geometry import dictionary
from .mixture import ExactMixtureFamily, mixture_weights


@dataclass(frozen=True)
class SplitSample:
    """Disjoint proposal/evaluation views and original row indices."""

    proposal: np.ndarray
    evaluation: np.ndarray
    proposal_indices: np.ndarray
    evaluation_indices: np.ndarray


def sample_latent(
    size: int,
    seed: int,
    *,
    p: float,
    nu: float,
    phi: float = FROZEN.phi_star,
    s: float = FROZEN.s,
) -> np.ndarray:
    """Generate observations directly from latent indicators and codes."""
    rng = np.random.default_rng(int(seed))
    design = dictionary(float(s), float(phi))
    indicators = rng.random((int(size), FROZEN.n)) < float(p)
    coefficients = indicators * rng.standard_normal((int(size), FROZEN.n))
    noise = math.sqrt(float(nu)) * rng.standard_normal((int(size), FROZEN.q))
    return coefficients @ design.T + noise


def sample_components(
    size: int,
    seed: int,
    *,
    p: float,
    nu: float,
    phi: float = FROZEN.phi_star,
    s: float = FROZEN.s,
) -> np.ndarray:
    """Generate observations by exact covariance-component sampling."""
    rng = np.random.default_rng(int(seed))
    family = ExactMixtureFamily.from_parameters(float(s))
    covariances = family.covariance_components(float(nu))
    factors = np.linalg.cholesky(covariances)
    components = rng.choice(32, size=int(size), p=mixture_weights(float(p)))
    standard = rng.standard_normal((int(size), FROZEN.q))
    values = np.empty_like(standard)
    for component in np.unique(components):
        locations = np.flatnonzero(components == component)
        values[locations] = standard[locations] @ factors[int(component)].T
    if float(phi) != 0.0:
        from .geometry import ambient_rotation

        values = values @ ambient_rotation(float(phi)).T
    return values


def split_sample(observations: np.ndarray, split_seed: int) -> SplitSample:
    """Apply the frozen seeded permutation and disjoint 45/55 split."""
    values = np.asarray(observations, dtype=float)
    permutation = np.random.default_rng(int(split_seed)).permutation(len(values))
    proposal_size = int(math.floor(FROZEN.proposal_fraction * len(values)))
    proposal_indices = permutation[:proposal_size]
    evaluation_indices = permutation[proposal_size:]
    return SplitSample(
        proposal=values[proposal_indices],
        evaluation=values[evaluation_indices],
        proposal_indices=proposal_indices,
        evaluation_indices=evaluation_indices,
    )
