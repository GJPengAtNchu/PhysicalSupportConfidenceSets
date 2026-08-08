"""Frozen tetrahedral geometry and compensated one-dimensional orbit."""

from __future__ import annotations

from itertools import permutations
import math

import numpy as np

from .config import FROZEN


OMEGA = np.asarray(
    [[0.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]],
    dtype=float,
)
ANCHOR = np.asarray([1.0, 0.0, 0.0, 1.0], dtype=float) / math.sqrt(2.0)


def tetrahedron_vertices() -> np.ndarray:
    """Return the four ordered regular-tetrahedron vertices as rows."""
    return np.asarray(
        [
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ],
        dtype=float,
    ) / math.sqrt(3.0)


def rotation(phi: float) -> np.ndarray:
    """Return `exp(phi Omega)`, the rotation around the first coordinate."""
    cosine = math.cos(float(phi))
    sine = math.sin(float(phi))
    return np.asarray(
        [[1.0, 0.0, 0.0], [0.0, cosine, -sine], [0.0, sine, cosine]],
        dtype=float,
    )


def ambient_rotation(phi: float) -> np.ndarray:
    """Embed the compensated rotation in the frozen four-dimensional space."""
    result = np.eye(4)
    result[:3, :3] = rotation(phi)
    return result


def dictionary(s: float, phi: float) -> np.ndarray:
    """Return the frozen `4 x 5` dictionary `D_phi` at collision scale `s`."""
    if not 0.0 < float(s) < 1.0:
        raise ValueError("s must belong to (0,1)")
    vertices = tetrahedron_vertices()
    transverse = float(s) * (vertices @ rotation(phi).T)
    axial = math.sqrt(1.0 - float(s) ** 2)
    children = np.column_stack(
        [np.concatenate((transverse[index], [axial])) for index in range(4)]
    )
    return np.column_stack((children, ANCHOR))


def rotated_observations(observations: np.ndarray, phi: float) -> np.ndarray:
    """Return `Q_phi^T y` rowwise, exploiting `D_phi=Q_phi D_0`."""
    values = np.asarray(observations, dtype=float)
    if values.ndim != 2 or values.shape[1] != 4:
        raise ValueError("observations must have shape (N,4)")
    cosine = math.cos(float(phi))
    sine = math.sin(float(phi))
    result = values.copy()
    result[:, 1] = cosine * values[:, 1] + sine * values[:, 2]
    result[:, 2] = -sine * values[:, 1] + cosine * values[:, 2]
    return result


def _golden_minimize(function: object, left: float, right: float) -> tuple[float, float]:
    """Deterministically minimize a scalar function on a bounded interval."""
    callback = function
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    a = float(left)
    b = float(right)
    c = b - ratio * (b - a)
    d = a + ratio * (b - a)
    fc = float(callback(c))  # type: ignore[operator]
    fd = float(callback(d))  # type: ignore[operator]
    for _ in range(100):
        if b - a <= 1.0e-14:
            break
        if fc <= fd:
            b, d, fd = d, c, fc
            c = b - ratio * (b - a)
            fc = float(callback(c))  # type: ignore[operator]
        else:
            a, c, fc = c, d, fd
            d = a + ratio * (b - a)
            fd = float(callback(d))  # type: ignore[operator]
    point = 0.5 * (a + b)
    return point, float(callback(point))  # type: ignore[operator]


def minimum_permutation_separation() -> dict[str, object]:
    """Minimize every nonidentity tetrahedral-permutation orbit residual."""
    vertices = tetrahedron_vertices()
    identity = tuple(range(4))
    records: list[dict[str, object]] = []
    for permutation in permutations(range(4)):
        if permutation == identity:
            continue
        target = vertices[np.asarray(permutation)]

        def residual(delta: float) -> float:
            moved = vertices @ rotation(delta).T
            return float(np.max(np.linalg.norm(moved - target, axis=1)))

        grid = np.linspace(
            FROZEN.phi_left - FROZEN.phi_right,
            FROZEN.phi_right - FROZEN.phi_left,
            4097,
        )
        values = np.asarray([residual(float(value)) for value in grid])
        index = int(np.argmin(values))
        lower = float(grid[max(0, index - 1)])
        upper = float(grid[min(len(grid) - 1, index + 1)])
        point, value = _golden_minimize(residual, lower, upper)
        records.append(
            {"permutation": list(permutation), "delta": point, "residual": value}
        )
    best = min(records, key=lambda item: float(item["residual"]))
    return {"minimum_residual": best["residual"], "closest": best, "all": records}


def verify_injective_domain(tolerance: float | None = None) -> dict[str, object]:
    """Verify the frozen interval has no nonidentity child-permutation collision."""
    limit = FROZEN.quotient_collision_tolerance if tolerance is None else tolerance
    result = minimum_permutation_separation()
    result["tolerance"] = float(limit)
    result["passed"] = bool(float(result["minimum_residual"]) > float(limit))
    return result
