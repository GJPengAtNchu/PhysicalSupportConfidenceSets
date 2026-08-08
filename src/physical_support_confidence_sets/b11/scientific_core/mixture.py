"""Exact variable-`p,nu` 32-component likelihood and normalized derivatives."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math

import numpy as np

from .config import FROZEN
from .geometry import dictionary
from .transforms import normalized_to_raw, raw_derivatives_from_normalized


def binary_masks() -> np.ndarray:
    """Return all 32 activation masks in a fixed lexicographic order."""
    return np.asarray(list(product((0, 1), repeat=FROZEN.n)), dtype=np.int8)


def mixture_weights(p: float) -> np.ndarray:
    """Return exact Bernoulli-product weights for all masks."""
    masks = binary_masks()
    sizes = masks.sum(axis=1)
    return np.asarray(
        float(p) ** sizes * (1.0 - float(p)) ** (FROZEN.n - sizes),
        dtype=float,
    )


def _logsumexp_rows(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return rowwise log-sum-exp and responsibilities."""
    maxima = np.max(values, axis=1)
    shifted = np.exp(values - maxima[:, None])
    totals = np.sum(shifted, axis=1)
    return maxima + np.log(totals), shifted / totals[:, None]


@dataclass(frozen=True)
class ExactMixtureFamily:
    """Exact signal covariances shared across the nuisance shell."""

    masks: np.ndarray
    sizes: np.ndarray
    signal_covariances: np.ndarray
    s: float

    @classmethod
    def from_parameters(cls, s: float = FROZEN.s) -> "ExactMixtureFamily":
        """Build all component signal covariances at orientation zero."""
        return cls.from_dictionary(dictionary(float(s), 0.0), s=float(s))

    @classmethod
    def from_dictionary(
        cls, base_dictionary: np.ndarray, *, s: float
    ) -> "ExactMixtureFamily":
        """Build the exact family from a supplied `4 x 5` dictionary."""
        design = np.asarray(base_dictionary, dtype=float)
        if design.shape != (FROZEN.q, FROZEN.n):
            raise ValueError("dictionary must have shape (4,5)")
        masks = binary_masks()
        signals = np.empty((len(masks), FROZEN.q, FROZEN.q), dtype=float)
        for index, mask in enumerate(masks):
            active = design[:, mask.astype(bool)]
            signals[index] = (
                active @ active.T
                if active.shape[1]
                else np.zeros((FROZEN.q, FROZEN.q), dtype=float)
            )
        return cls(
            masks=masks,
            sizes=masks.sum(axis=1).astype(float),
            signal_covariances=signals,
            s=float(s),
        )

    def covariance_components(self, nu: float) -> np.ndarray:
        """Return all 32 candidate covariances at raw noise variance `nu`."""
        if float(nu) <= 0.0:
            raise ValueError("nu must be positive")
        return self.signal_covariances + float(nu) * np.eye(FROZEN.q)[None, :, :]

    def cache(self, observations: np.ndarray) -> "VariableMixtureCache":
        """Attach observations to this exact candidate family."""
        return VariableMixtureCache.from_observations(self, observations)


@dataclass(frozen=True)
class VariableMixtureCache:
    """Observation cache for exact likelihood, gradient, and Hessian calls."""

    family: ExactMixtureFamily
    observations: np.ndarray
    observation_norm_squared: np.ndarray

    @classmethod
    def from_observations(
        cls, family: ExactMixtureFamily, observations: np.ndarray
    ) -> "VariableMixtureCache":
        """Validate and cache one ordered observation matrix."""
        values = np.asarray(observations, dtype=float)
        if values.ndim != 2 or values.shape[1] != FROZEN.q:
            raise ValueError("observations must have shape (N,4)")
        return cls(
            family=family,
            observations=values,
            observation_norm_squared=np.sum(values**2, axis=1),
        )

    @property
    def size(self) -> int:
        """Return the cached observation count."""
        return int(self.observations.shape[0])

    def _rotated_triplet(
        self, phi: float
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return `Q_phi^T y` and its first two raw-phi derivatives."""
        values = self.observations
        cosine = math.cos(float(phi))
        sine = math.sin(float(phi))
        rotated = values.copy()
        rotated[:, 1] = cosine * values[:, 1] + sine * values[:, 2]
        rotated[:, 2] = -sine * values[:, 1] + cosine * values[:, 2]
        first = np.zeros_like(rotated)
        first[:, 1] = rotated[:, 2]
        first[:, 2] = -rotated[:, 1]
        second = np.zeros_like(rotated)
        second[:, 1] = -rotated[:, 1]
        second[:, 2] = -rotated[:, 2]
        return rotated, first, second

    def evaluate_raw(
        self,
        phi: float,
        p: float,
        nu: float,
        *,
        derivatives: bool = True,
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
        """Evaluate exact density and raw-coordinate derivatives pointwise."""
        probability = float(p)
        noise = float(nu)
        if not (
            FROZEN.p_left <= probability <= FROZEN.p_right
            and FROZEN.nu_left <= noise <= FROZEN.nu_right
        ):
            raise ValueError("nuisance candidate lies outside the frozen shell")
        covariances = self.family.covariance_components(noise)
        signs, log_determinants = np.linalg.slogdet(covariances)
        if not np.all(signs > 0.0):
            raise ArithmeticError("a component covariance is not SPD")
        inverses = np.linalg.inv(covariances)
        sizes = self.family.sizes
        log_weights = (
            sizes * math.log(probability)
            + (FROZEN.n - sizes) * math.log(1.0 - probability)
        )
        rotated, first_phi, second_phi = self._rotated_triplet(float(phi))
        quadratic = np.einsum(
            "ni,mij,nj->nm", rotated, inverses, rotated, optimize=True
        )
        component_values = log_weights[None, :] - 0.5 * (
            FROZEN.q * math.log(2.0 * math.pi)
            + log_determinants[None, :]
            + quadratic
        )
        log_density, responsibilities = _logsumexp_rows(component_values)
        if not derivatives:
            return log_density, None, None

        inverse_two = np.matmul(inverses, inverses)
        inverse_three = np.matmul(inverse_two, inverses)
        q_phi = 2.0 * np.einsum(
            "ni,mij,nj->nm", first_phi, inverses, rotated, optimize=True
        )
        q_phi_phi = 2.0 * (
            np.einsum(
                "ni,mij,nj->nm", second_phi, inverses, rotated, optimize=True
            )
            + np.einsum(
                "ni,mij,nj->nm", first_phi, inverses, first_phi, optimize=True
            )
        )
        quadratic_two = np.einsum(
            "ni,mij,nj->nm", rotated, inverse_two, rotated, optimize=True
        )
        quadratic_three = np.einsum(
            "ni,mij,nj->nm", rotated, inverse_three, rotated, optimize=True
        )
        cross_phi_nu = np.einsum(
            "ni,mij,nj->nm", first_phi, inverse_two, rotated, optimize=True
        )
        trace_inverse = np.trace(inverses, axis1=1, axis2=2)
        trace_inverse_two = np.trace(inverse_two, axis1=1, axis2=2)

        g_phi = -0.5 * q_phi
        g_p = sizes / probability - (FROZEN.n - sizes) / (
            1.0 - probability
        )
        g_nu = -0.5 * trace_inverse[None, :] + 0.5 * quadratic_two
        h_phi_phi = -0.5 * q_phi_phi
        h_p_p = -sizes / probability**2 - (FROZEN.n - sizes) / (
            1.0 - probability
        ) ** 2
        h_nu_nu = 0.5 * trace_inverse_two[None, :] - quadratic_three

        gradient_raw = np.column_stack(
            (
                np.sum(responsibilities * g_phi, axis=1),
                np.sum(responsibilities * g_p[None, :], axis=1),
                np.sum(responsibilities * g_nu, axis=1),
            )
        )
        hessian_raw = np.zeros((self.size, 3, 3), dtype=float)
        hessian_raw[:, 0, 0] = np.sum(
            responsibilities * (h_phi_phi + g_phi**2), axis=1
        ) - gradient_raw[:, 0] ** 2
        hessian_raw[:, 1, 1] = np.sum(
            responsibilities * (h_p_p[None, :] + g_p[None, :] ** 2),
            axis=1,
        ) - gradient_raw[:, 1] ** 2
        hessian_raw[:, 2, 2] = np.sum(
            responsibilities * (h_nu_nu + g_nu**2), axis=1
        ) - gradient_raw[:, 2] ** 2
        hessian_raw[:, 0, 1] = np.sum(
            responsibilities * g_phi * g_p[None, :], axis=1
        ) - gradient_raw[:, 0] * gradient_raw[:, 1]
        hessian_raw[:, 0, 2] = np.sum(
            responsibilities * (cross_phi_nu + g_phi * g_nu), axis=1
        ) - gradient_raw[:, 0] * gradient_raw[:, 2]
        hessian_raw[:, 1, 2] = np.sum(
            responsibilities * g_p[None, :] * g_nu, axis=1
        ) - gradient_raw[:, 1] * gradient_raw[:, 2]
        hessian_raw[:, 1, 0] = hessian_raw[:, 0, 1]
        hessian_raw[:, 2, 0] = hessian_raw[:, 0, 2]
        hessian_raw[:, 2, 1] = hessian_raw[:, 1, 2]
        return log_density, gradient_raw, hessian_raw

    def evaluate(
        self, x: np.ndarray, *, derivatives: bool = True
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
        """Evaluate density and derivatives in normalized coordinates."""
        point = np.asarray(x, dtype=float)
        phi, p, nu = normalized_to_raw(point)
        values, gradient_raw, hessian_raw = self.evaluate_raw(
            phi, p, nu, derivatives=derivatives
        )
        if not derivatives:
            return values, None, None
        assert gradient_raw is not None and hessian_raw is not None
        first, second = raw_derivatives_from_normalized(point)
        gradient = gradient_raw * first[None, :]
        hessian = (
            hessian_raw
            * first[None, :, None]
            * first[None, None, :]
        )
        diagonal = np.arange(3)
        hessian[:, diagonal, diagonal] += gradient_raw * second[None, :]
        return values, gradient, hessian

    def log_likelihood(
        self, x: np.ndarray, *, derivatives: bool = False
    ) -> tuple[float, np.ndarray | None, np.ndarray | None]:
        """Return total log likelihood and optional normalized derivatives."""
        values, gradient, hessian = self.evaluate(x, derivatives=derivatives)
        likelihood = float(np.sum(values))
        if not derivatives:
            return likelihood, None, None
        assert gradient is not None and hessian is not None
        return likelihood, np.sum(gradient, axis=0), np.sum(hessian, axis=0)

    def log_likelihood_checkpoints(
        self,
        x: np.ndarray,
        checkpoints: np.ndarray,
        *,
        derivatives: bool = True,
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
        """Return prefix likelihood, gradient, and Hessian at checkpoints."""
        indices = np.asarray(checkpoints, dtype=int) - 1
        if np.any(indices < 0) or np.any(indices >= self.size):
            raise ValueError("checkpoint outside cached sample")
        values, gradient, hessian = self.evaluate(x, derivatives=derivatives)
        likelihood = np.cumsum(values)[indices]
        if not derivatives:
            return likelihood, None, None
        assert gradient is not None and hessian is not None
        return (
            likelihood,
            np.cumsum(gradient, axis=0)[indices],
            np.cumsum(hessian, axis=0)[indices],
        )

    def global_hessian_envelope(self) -> np.ndarray:
        """Return a deterministic shell-uniform normalized Hessian bound."""
        norm_two = self.observation_norm_squared
        nu_min = FROZEN.nu_left
        p_min = FROZEN.p_left
        p_max = FROZEN.p_right
        raw_gradient = np.column_stack(
            (
                norm_two / nu_min,
                np.full(
                    self.size,
                    FROZEN.n / p_min + FROZEN.n / (1.0 - p_max),
                ),
                0.5
                * (
                    FROZEN.q / nu_min
                    + norm_two / nu_min**2
                ),
            )
        )
        raw_hessian = np.zeros((self.size, 3, 3), dtype=float)
        raw_hessian[:, 0, 0] = 2.0 * norm_two / nu_min
        raw_hessian[:, 1, 1] = (
            FROZEN.n / p_min**2
            + FROZEN.n / (1.0 - p_max) ** 2
        )
        raw_hessian[:, 2, 2] = (
            0.5 * FROZEN.q / nu_min**2
            + norm_two / nu_min**3
        )
        raw_hessian[:, 0, 2] = norm_two / nu_min**2
        raw_hessian[:, 2, 0] = raw_hessian[:, 0, 2]
        transform_first_max = np.asarray(
            [
                0.4,
                0.5
                * (
                    math.log(FROZEN.p_right / (1.0 - FROZEN.p_right))
                    - math.log(FROZEN.p_left / (1.0 - FROZEN.p_left))
                )
                * 0.25,
                0.5
                * math.log(FROZEN.nu_right / FROZEN.nu_left)
                * FROZEN.nu_right,
            ]
        )
        transform_second_max = np.asarray(
            [
                0.0,
                (
                    0.5
                    * (
                        math.log(FROZEN.p_right / (1.0 - FROZEN.p_right))
                        - math.log(FROZEN.p_left / (1.0 - FROZEN.p_left))
                    )
                )
                ** 2
                * 0.25,
                (
                    0.5
                    * math.log(FROZEN.nu_right / FROZEN.nu_left)
                )
                ** 2
                * FROZEN.nu_right,
            ]
        )
        transformed_hessian = (
            raw_hessian
            * transform_first_max[None, :, None]
            * transform_first_max[None, None, :]
        )
        transformed_hessian[:, np.arange(3), np.arange(3)] += (
            raw_gradient * transform_second_max[None, :]
        )
        component_hessian_norm = np.linalg.norm(
            transformed_hessian, axis=(1, 2)
        )
        transformed_gradient = raw_gradient * transform_first_max[None, :]
        mixture_covariance_bound = np.sum(
            transformed_gradient**2, axis=1
        )
        return np.nextafter(
            component_hessian_norm + mixture_covariance_bound, np.inf
        )
