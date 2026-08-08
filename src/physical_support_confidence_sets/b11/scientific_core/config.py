"""Frozen constants and paths for LA1.3-ARA-G0.1.

Every carrier, metric, proposal, optimizer, and ARA-search constant below is
inherited unchanged from G0. Only experiment paths/version and the separated
reference lifecycle fields are new.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
HANDOFF = WORKSPACE / "LA1_3_ARA_G01_CODEX_HANDOFF"
G0_BASELINE = WORKSPACE / "la1_3_ara_g0"
ARTIFACT_ROOT = ROOT / "artifacts" / "la1_3_ara_g01"
SEED_PATH = ROOT / "configs" / "frozen_seeds.json"


@dataclass(frozen=True)
class FrozenConfig:
    """Typed union of the inherited carrier and frozen G0.1 contract."""

    experiment_id: str = "LA1_3_ARA_G01"
    version: str = "G0.1"

    # Inherited statistical carrier.
    q: int = 4
    n: int = 5
    s: float = 0.4
    phi_star: float = 0.0
    phi_left: float = -0.4
    phi_right: float = 0.4
    p_star: float = 0.20
    nu_star: float = 1.00
    p_left: float = 0.15
    p_right: float = 0.30
    nu_left: float = 0.80
    nu_right: float = 1.20
    proposal_fraction: float = 0.45
    alpha_d: float = 0.077
    checkpoint_minimum: int = 128
    smoke_n: int = 4096
    primary_n: int = 65536

    # Inherited operational proposal and reference mathematics.
    proposal_sobol_points: int = 128
    proposal_local_starts: int = 12
    proposal_audit_local_starts: int = 16
    reference_temperature: float = 0.05
    reference_refine_width: float = 1.0e-4

    # Inherited numerical tolerances.
    transform_tolerance: float = 5.0e-14
    unit_norm_tolerance: float = 5.0e-14
    weight_sum_tolerance: float = 5.0e-15
    logdensity_abs_tolerance: float = 1.0e-9
    logdensity_relative_tolerance: float = 1.0e-10
    gradient_relative_tolerance: float = 2.0e-5
    hessian_relative_tolerance: float = 2.0e-4
    hessian_absolute_tolerance: float = 1.0e-6
    hessian_symmetry_tolerance: float = 1.0e-10
    quotient_collision_tolerance: float = 1.0e-10
    audit_boundary_tolerance: float = 1.0e-10

    # Physical metric and data-free shell diameter.
    active_support_zero_based: tuple[int, int] = (0, 1)
    geometry_grid_points: int = 4097
    geometry_local_refinement_starts: int = 32
    resolution_fractions: tuple[float, ...] = (
        0.10,
        0.20,
        0.30,
        0.40,
        0.50,
    )

    # Unified safe optimizer.
    bound_tolerance: float = 1.0e-10

    # Frozen ARA starts, orders, refinements, and caps.
    initial_phi_probes: tuple[float, ...] = (
        -0.4,
        0.4,
        -0.3,
        0.3,
        -0.2,
        0.2,
        -0.1,
        0.1,
        0.0,
    )
    nuisance_sobol_starts: int = 12
    nuisance_coordinate_grid_points: int = 17
    nuisance_max_sweeps: int = 3
    nuisance_pairwise_local_starts: int = 4
    smooth_max_temperature: float = 0.05
    coordinate_orders: tuple[tuple[str, str, str], ...] = (
        ("phi", "p", "nu"),
        ("phi", "nu", "p"),
        ("p", "nu", "phi"),
        ("nu", "p", "phi"),
    )
    maximum_sweeps_per_order: int = 4
    phi_grid_points: int = 33
    maximum_anchors: int = 4
    improvement_tolerance_fraction: float = 1.0e-4
    near_shell_diameter_stop_fraction: float = 0.98
    maximum_double_precision_evaluations: int = 10_000
    maximum_high_precision_replays: int = 96
    maximum_accepted_witnesses: int = 32
    ara_wall_seconds_cap: float = 1200.0
    smoke_wall_seconds_cap: float = 900.0
    memory_gb_cap: float = 8.0
    duplicate_normalized_distance: float = 1.0e-8

    # Fixed-pool replay.
    alpha_grid: tuple[float, ...] = (0.025, 0.05, 0.077, 0.10, 0.15)

    # Frozen terminal gates.
    informative_diameter_fraction: float = 0.20
    informative_required_runs: int = 4
    minimum_median_diameter_recall: float = 0.85
    minimum_pooled_threshold_recall: float = 0.90
    maximum_median_runtime_ratio: float = 0.30
    ara_resource_hit_hold_count: int = 3
    reference_failure_hold_count: int = 2

    # G0.1 reference-validation lifecycle only; no ARA constant changes.
    reference_wall_seconds_cap: float = 3600.0
    required_completed_references: int = 4
    reference_initial_indices: tuple[int, ...] = (1, 2, 3, 4)
    reference_reserve_indices: tuple[int, ...] = (5, 6)

    @property
    def threshold(self) -> float:
        """Return the frozen primary log-e boundary."""
        return math.log(1.0 / self.alpha_d)

    def maximum_wall_seconds(self, sample_size: int) -> float:
        """Return the ARA wall cap (the smoke lifecycle has a tighter gate)."""
        del sample_size
        return self.ara_wall_seconds_cap

    def proposal_audit_points(self, sample_size: int) -> int:
        """Return the inherited independent proposal-audit Sobol count."""
        if sample_size <= 16384:
            return 512
        if sample_size == 65536:
            return 128
        return 64

    def reference_phi_points(self, sample_size: int) -> int:
        """Return the inherited pointwise-reference orientation-grid size."""
        if sample_size <= 16384:
            return 65
        if sample_size == 65536:
            return 33
        return 17

    def reference_sobol_points(self, sample_size: int) -> int:
        """Return the inherited pointwise-reference global Sobol count."""
        if sample_size <= 16384:
            return 1024
        if sample_size == 65536:
            return 256
        return 128


FROZEN = FrozenConfig()
