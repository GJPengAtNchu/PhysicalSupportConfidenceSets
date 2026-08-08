"""Public projective physical distance for the active two-ray carrier."""

from __future__ import annotations

from dataclasses import dataclass
import math


Vector = tuple[float, float, float, float]
RaySet = tuple[Vector, Vector]


def _active_rays(collision_scale: float, phi: float) -> RaySet:
    """Return the inherited active child rays ``S={1,2}``.

    The formula is reproduced here with only Python's standard library so the
    public geometry package has no path into a scientific scorer or oracle.
    """

    scale = float(collision_scale)
    if not 0.0 < scale < 1.0:
        raise ValueError("collision_scale must belong to (0,1)")
    cosine = math.cos(float(phi))
    sine = math.sin(float(phi))
    axial = math.sqrt(1.0 - scale * scale)
    root_three = math.sqrt(3.0)
    rays: list[Vector] = []
    for x0, x1, x2 in ((1.0, 1.0, 1.0), (1.0, -1.0, -1.0)):
        rotated_1 = cosine * x1 - sine * x2
        rotated_2 = sine * x1 + cosine * x2
        rays.append(
            (
                scale * x0 / root_three,
                scale * rotated_1 / root_three,
                scale * rotated_2 / root_three,
                axial,
            )
        )
    return (rays[0], rays[1])


def _projective_distance(left: Vector, right: Vector) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    cosine = min(1.0, max(0.0, abs(dot / (left_norm * right_norm))))
    return math.sqrt(max(0.0, 1.0 - cosine * cosine))


@dataclass(frozen=True)
class ProjectiveOrientationMetric:
    """Scenario-specific, score-free physical metric."""

    collision_scale: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.collision_scale) or not (
            0.0 < self.collision_scale < 1.0
        ):
            raise ValueError("collision_scale must belong to (0,1)")

    def distance(self, phi: float, other_phi: float) -> float:
        left = _active_rays(self.collision_scale, float(phi))
        right = _active_rays(self.collision_scale, float(other_phi))
        pairwise = tuple(
            tuple(_projective_distance(a, b) for b in right) for a in left
        )
        row_directed = max(min(row) for row in pairwise)
        column_directed = max(
            min(pairwise[row][column] for row in range(2))
            for column in range(2)
        )
        return max(row_directed, column_directed)

    def grid_shell_diameter(
        self,
        phi_values: tuple[float, ...],
    ) -> float:
        if not phi_values:
            raise ValueError("phi_values must be nonempty")
        return max(
            self.distance(left, right)
            for left_index, left in enumerate(phi_values)
            for right in phi_values[left_index:]
        )
