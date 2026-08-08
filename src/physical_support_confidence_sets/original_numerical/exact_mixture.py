"""Exact likelihoods and stable pairwise information estimates."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
from numpy.polynomial.hermite import hermgauss
from scipy.special import logsumexp

from .geometry import balanced_dictionary


@dataclass(frozen=True)
class GaussianMixture:
    weights: np.ndarray
    covariances: np.ndarray
    inverses: np.ndarray
    log_determinants: np.ndarray
    cholesky_factors: np.ndarray

    @classmethod
    def bernoulli_gaussian(
        cls,
        s: float,
        angle: float,
        p: float,
        nu: float,
        coefficient_variance: float = 1.0,
        lambda_star: float = 1.0,
    ) -> "GaussianMixture":
        if not 0.0 < p < 1.0:
            raise ValueError("p must belong to (0,1)")
        if nu <= 0.0:
            raise ValueError("nu must be positive")
        dictionary = balanced_dictionary(s, angle, lambda_star)
        masks = np.asarray(list(product([0, 1], repeat=dictionary.shape[1])), dtype=float)
        sizes = masks.sum(axis=1)
        weights = p**sizes * (1.0 - p) ** (dictionary.shape[1] - sizes)
        covariances = np.empty((len(masks), dictionary.shape[0], dictionary.shape[0]))
        for index, mask in enumerate(masks):
            active = dictionary[:, mask.astype(bool)]
            covariances[index] = nu * np.eye(dictionary.shape[0])
            if active.shape[1]:
                covariances[index] += coefficient_variance * (active @ active.T)
        inverses = np.linalg.inv(covariances)
        signs, log_determinants = np.linalg.slogdet(covariances)
        if not np.all(signs > 0):
            raise ArithmeticError("non-positive mixture covariance")
        cholesky_factors = np.linalg.cholesky(covariances)
        return cls(weights, covariances, inverses, log_determinants, cholesky_factors)

    @property
    def dimension(self) -> int:
        return int(self.covariances.shape[1])

    def logpdf(self, observations: np.ndarray) -> np.ndarray:
        observations = np.atleast_2d(np.asarray(observations, dtype=float))
        quadratic = np.einsum(
            "mi,kij,mj->mk", observations, self.inverses, observations, optimize=True
        )
        constants = self.dimension * np.log(2.0 * np.pi) + self.log_determinants
        component_logpdf = (
            np.log(self.weights)[None, :] - 0.5 * (constants[None, :] + quadratic)
        )
        return logsumexp(component_logpdf, axis=1)

    def sample(self, size: int, rng: np.random.Generator) -> np.ndarray:
        components = rng.choice(len(self.weights), size=size, p=self.weights)
        standard = rng.normal(size=(size, self.dimension))
        observations = np.empty_like(standard)
        for component in np.unique(components):
            locations = np.flatnonzero(components == component)
            observations[locations] = (
                standard[locations] @ self.cholesky_factors[component].T
            )
        return observations


def _sech(values: np.ndarray) -> np.ndarray:
    """Stable hyperbolic secant."""
    return np.exp(-(np.logaddexp(values, -values) - np.log(2.0)))


def midpoint_pair_batch(
    first: GaussianMixture,
    second: GaussianMixture,
    size: int,
    rng: np.random.Generator,
) -> dict[str, float]:
    """One iid batch from m=(P+Q)/2 with nonnegative diagnostics."""
    if first.dimension != second.dimension:
        raise ValueError("mixture dimensions differ")
    if size % 2:
        raise ValueError("midpoint batch size must be even")
    endpoints = np.repeat([0, 1], size // 2)
    rng.shuffle(endpoints)
    observations = np.empty((size, first.dimension))
    first_locations = np.flatnonzero(endpoints == 0)
    second_locations = np.flatnonzero(endpoints == 1)
    if len(first_locations):
        observations[first_locations] = first.sample(len(first_locations), rng)
    if len(second_locations):
        observations[second_locations] = second.sample(len(second_locations), rng)
    likelihood_ratio = first.logpdf(observations) - second.logpdf(observations)
    jeffreys_terms = 2.0 * likelihood_ratio * np.tanh(likelihood_ratio / 2.0)
    half_ratio = likelihood_ratio / 2.0
    affinity_deficit_terms = np.tanh(half_ratio) ** 2 / (1.0 + _sech(half_ratio))
    # Tiny negative roundoff would violate the identity's useful invariant.
    if np.min(jeffreys_terms) < -1e-13 or np.min(affinity_deficit_terms) < -1e-15:
        raise ArithmeticError("nonnegative pair identity failed numerically")
    return {
        "jeffreys": float(np.mean(np.maximum(jeffreys_terms, 0.0))),
        "affinity_deficit": float(
            np.mean(np.maximum(affinity_deficit_terms, 0.0))
        ),
        "likelihood_ratio_second_moment": float(np.mean(likelihood_ratio**2)),
        "maximum_absolute_likelihood_ratio": float(
            np.max(np.abs(likelihood_ratio))
        ),
    }


def estimate_pair_batches(
    first: GaussianMixture,
    second: GaussianMixture,
    batches: int,
    batch_size: int,
    seed: int,
) -> list[dict[str, float]]:
    seed_sequence = np.random.SeedSequence(seed)
    children = seed_sequence.spawn(batches)
    estimates = []
    for batch_index, child in enumerate(children):
        estimate = midpoint_pair_batch(
            first, second, batch_size, np.random.default_rng(child)
        )
        estimate["batch"] = batch_index
        estimate["batch_size"] = batch_size
        estimates.append(estimate)
    return estimates


def product_affinity_deficit(single_deficit: np.ndarray | float, sample_size: np.ndarray | float) -> np.ndarray:
    """Return 1-(1-single_deficit)^sample_size without cancellation."""
    single_deficit = np.asarray(single_deficit, dtype=float)
    sample_size = np.asarray(sample_size, dtype=float)
    if np.any((single_deficit < 0.0) | (single_deficit >= 1.0)):
        raise ValueError("single-observation affinity deficit must lie in [0,1)")
    return -np.expm1(sample_size * np.log1p(-single_deficit))


def gauss_hermite_pair_diagnostics(
    first: GaussianMixture,
    second: GaussianMixture,
    order: int,
    chunk_size: int = 8192,
) -> dict[str, float]:
    """Tensor Gauss-Hermite integration under m=(P+Q)/2."""
    if first.dimension != second.dimension:
        raise ValueError("mixture dimensions differ")
    nodes_1d, weights_1d = hermgauss(order)
    node_mesh = np.meshgrid(*([nodes_1d] * first.dimension), indexing="ij")
    weight_mesh = np.meshgrid(*([weights_1d] * first.dimension), indexing="ij")
    nodes = np.column_stack([item.ravel() for item in node_mesh])
    weights = np.prod(np.stack(weight_mesh, axis=0), axis=0).ravel()
    weights /= np.pi ** (first.dimension / 2.0)

    jeffreys = 0.0
    affinity_deficit = 0.0
    for endpoint in (first, second):
        for component, component_weight in enumerate(endpoint.weights):
            subtotal_j = 0.0
            subtotal_a = 0.0
            for start in range(0, len(nodes), chunk_size):
                stop = min(start + chunk_size, len(nodes))
                observations = (
                    np.sqrt(2.0)
                    * nodes[start:stop]
                    @ endpoint.cholesky_factors[component].T
                )
                likelihood_ratio = first.logpdf(observations) - second.logpdf(
                    observations
                )
                half_ratio = likelihood_ratio / 2.0
                terms_j = 2.0 * likelihood_ratio * np.tanh(half_ratio)
                terms_a = np.tanh(half_ratio) ** 2 / (1.0 + _sech(half_ratio))
                subtotal_j += float(weights[start:stop] @ terms_j)
                subtotal_a += float(weights[start:stop] @ terms_a)
            jeffreys += 0.5 * float(component_weight) * subtotal_j
            affinity_deficit += 0.5 * float(component_weight) * subtotal_a
    return {
        "jeffreys": jeffreys,
        "affinity_deficit": affinity_deficit,
        "order": int(order),
    }
