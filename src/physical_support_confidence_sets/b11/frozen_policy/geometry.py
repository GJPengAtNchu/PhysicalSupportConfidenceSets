"""Frozen data-free physical orientation metric."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Hashable, Sequence


Vector = tuple[float, float, float, float]
Point = tuple[Hashable, float]


@lru_cache(maxsize=None)
def active_rays(scale: float, phi: float) -> tuple[Vector, Vector]:
    axial = math.sqrt(1.0 - scale * scale)
    root_three = math.sqrt(3.0)
    cosine = math.cos(phi)
    sine = math.sin(phi)
    rows: list[Vector] = []
    for x0, x1, x2 in ((1.0, 1.0, 1.0), (1.0, -1.0, -1.0)):
        rows.append(
            (
                scale * x0 / root_three,
                scale * (cosine * x1 - sine * x2) / root_three,
                scale * (sine * x1 + cosine * x2) / root_three,
                axial,
            )
        )
    return rows[0], rows[1]


def ray_distance(left: Vector, right: Vector) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    cosine = min(1.0, max(0.0, abs(dot / (left_norm * right_norm))))
    return math.sqrt(max(0.0, 1.0 - cosine * cosine))


@lru_cache(maxsize=None)
def physical_distance(scale: float, phi: float, other_phi: float) -> float:
    left = active_rays(scale, phi)
    right = active_rays(scale, other_phi)
    pairwise = tuple(
        tuple(ray_distance(item, other) for other in right) for item in left
    )
    row_directed = max(min(row) for row in pairwise)
    column_directed = max(
        min(pairwise[row][column] for row in range(2))
        for column in range(2)
    )
    return max(row_directed, column_directed)


def canonical_diameter(
    scale: float,
    points: Sequence[Point],
) -> tuple[float, tuple[Hashable, ...]]:
    """Return a deterministic finite-pool diameter and canonical endpoints."""

    if not points:
        raise ValueError("diameter pool must contain the proposal")
    if len(points) == 1:
        return 0.0, (points[0][0],)
    best_distance = -1.0
    best_pair: tuple[Hashable, Hashable] | None = None
    for left in range(len(points)):
        for right in range(left + 1, len(points)):
            distance = physical_distance(scale, points[left][1], points[right][1])
            pair = (points[left][0], points[right][0])
            if (
                distance > best_distance + 1.0e-16
                or (
                    abs(distance - best_distance) <= 1.0e-16
                    and repr(pair) < repr(best_pair)
                )
            ):
                best_distance = distance
                best_pair = pair
    if best_pair is None:
        raise AssertionError("diameter endpoint selection failed")
    return best_distance, best_pair


def shell_diameter(scale: float, orientations: Sequence[float]) -> float:
    unique = tuple(sorted(set(float(value) for value in orientations)))
    if len(unique) < 2:
        return 0.0
    return max(
        physical_distance(scale, unique[left], unique[right])
        for left in range(len(unique))
        for right in range(left + 1, len(unique))
    )
