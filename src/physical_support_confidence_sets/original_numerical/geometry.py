"""Balanced-hard-core geometry used by the frozen pilot."""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment


def tetrahedron_vertices() -> np.ndarray:
    """Return the q=4 regular-simplex vertices as rows in U=R^3."""
    return np.asarray(
        [
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ]
    ) / np.sqrt(3.0)


def rotation_about_axis(axis: np.ndarray, angle: float) -> np.ndarray:
    """Rodrigues rotation with angle measured in radians."""
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    x, y, z = axis
    cross = np.asarray([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
    return (
        np.eye(3) * np.cos(angle)
        + (1.0 - np.cos(angle)) * np.outer(axis, axis)
        + np.sin(angle) * cross
    )


def compensated_rotation(angle: float) -> np.ndarray:
    """Rotate about v1+v2, fixing the equal-coefficient support mean."""
    vertices = tetrahedron_vertices()
    return rotation_about_axis(vertices[0] + vertices[1], angle)


def balanced_dictionary(
    s: float, angle: float = 0.0, lambda_star: float = 1.0
) -> np.ndarray:
    """Return D in R^{4 x 5}: four coherent children and one anchor."""
    radius = lambda_star * float(s)
    if not 0.0 < radius < 1.0:
        raise ValueError("lambda_star * s must belong to (0,1)")
    vertices = tetrahedron_vertices()
    rotation = compensated_rotation(angle)
    transverse = radius * (vertices @ rotation.T)
    axial = np.sqrt(1.0 - radius**2)
    children = np.column_stack(
        [np.concatenate([transverse[j], [axial]]) for j in range(4)]
    )
    anchor = np.asarray([1.0, 0.0, 0.0, 1.0]) / np.sqrt(2.0)
    return np.column_stack([children, anchor])


def sparse_mean(dictionary: np.ndarray, support: list[int], coefficients: np.ndarray) -> np.ndarray:
    coefficients = np.asarray(coefficients, dtype=float)
    return dictionary[:, support] @ coefficients


def parent_pair(
    s: float,
    beta: float = 1.0,
    support: tuple[int, int] = (0, 1),
    lambda_star: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Fine mean and its closest point on the fixed anchor line."""
    dictionary = balanced_dictionary(s, lambda_star=lambda_star)
    fine = sparse_mean(dictionary, list(support), beta * np.ones(len(support)))
    anchor = dictionary[:, -1]
    gamma = float(anchor @ fine)
    return fine, gamma * anchor


def wrong_support_pair(
    s: float,
    beta: float = 1.0,
    support: tuple[int, int] = (0, 1),
    alternative: tuple[int, int] = (0, 2),
    lambda_star: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    dictionary = balanced_dictionary(s, lambda_star=lambda_star)
    first = sparse_mean(dictionary, list(support), beta * np.ones(len(support)))
    second = sparse_mean(
        dictionary, list(alternative), beta * np.ones(len(alternative))
    )
    return first, second


def profiled_task_residual(
    s: float,
    angle: float,
    mean_coefficient: float,
    contrast: float,
    support: tuple[int, int] = (0, 1),
    lambda_star: float = 1.0,
) -> tuple[float, float]:
    """Numerical and analytic two-atom coefficient-profiled residuals."""
    x = np.asarray(
        [mean_coefficient + contrast / 2.0, mean_coefficient - contrast / 2.0]
    )
    dictionary_zero = balanced_dictionary(s, 0.0, lambda_star)
    dictionary_angle = balanced_dictionary(s, angle, lambda_star)
    target = sparse_mean(dictionary_zero, list(support), x)
    design = dictionary_angle[:, list(support)]
    fitted_coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
    numerical = float(np.linalg.norm(target - design @ fitted_coefficients))
    vertices = tetrahedron_vertices()
    analytic = (
        lambda_star
        * s
        * abs(contrast)
        * np.linalg.norm(vertices[support[0]] - vertices[support[1]])
        * abs(np.sin(angle))
        / 2.0
    )
    return numerical, float(analytic)


def affinity_deficit_from_gaussian_replicates(
    mean_zero: np.ndarray, mean_one: np.ndarray, replicates: float, sigma: float
) -> float:
    """Return 1-BC for equal-covariance Gaussian product experiments."""
    exponent = -float(replicates) * np.linalg.norm(mean_zero - mean_one) ** 2
    exponent /= 8.0 * sigma**2
    return float(-np.expm1(exponent))


def projective_matching(
    s: float, angle: float, lambda_star: float = 1.0
) -> tuple[np.ndarray, float, float]:
    """Optimal child matching and the identity-vs-next-best assignment gap."""
    first = balanced_dictionary(s, 0.0, lambda_star)[:, :4]
    second = balanced_dictionary(s, angle, lambda_star)[:, :4]
    inner = np.clip(first.T @ second, -1.0, 1.0)
    costs = np.sqrt(np.maximum(0.0, 1.0 - inner**2))
    rows, columns = linear_sum_assignment(costs)
    optimal = float(costs[rows, columns].sum())
    identity = float(np.trace(costs))
    alternatives = []
    from itertools import permutations

    for permutation in permutations(range(4)):
        if tuple(permutation) == tuple(columns):
            continue
        alternatives.append(float(costs[np.arange(4), permutation].sum()))
    next_best = min(alternatives)
    return columns, identity - optimal, next_best - optimal
