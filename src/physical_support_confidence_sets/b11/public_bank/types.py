"""Strict public capabilities and immutable ARA-bank inputs."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CandidateScore:
    """Checkpoint scores for exactly one requested bank candidate."""

    candidate_id: int
    checkpoint_log_e: tuple[float, ...]
    numerically_valid: bool = True

    def __post_init__(self) -> None:
        if self.candidate_id < 0:
            raise ValueError("candidate_id must be nonnegative")
        if not self.checkpoint_log_e:
            raise ValueError("checkpoint_log_e must be nonempty")
        if self.numerically_valid and not all(
            math.isfinite(value) for value in self.checkpoint_log_e
        ):
            raise ValueError("valid checkpoint scores must be finite")


@dataclass(frozen=True)
class ReplayDecision:
    """Independent pointwise replay for one previously queried candidate."""

    candidate_id: int
    admissible: bool
    precision_decimal_digits: int
    maximum_rejection_margin: str

    def __post_init__(self) -> None:
        if self.candidate_id < 0:
            raise ValueError("candidate_id must be nonnegative")
        if self.precision_decimal_digits != 90:
            raise ValueError("B0 witness replay must use exactly 90 digits")
        if not self.maximum_rejection_margin:
            raise ValueError("maximum_rejection_margin must be recorded")


@runtime_checkable
class QueryPort(Protocol):
    """The complete data-dependent capability visible to ARA-bank."""

    def query(self, candidate_id: int) -> CandidateScore:
        """Return scores for this candidate and no other bank state."""

    def replay_queried_witness(
        self,
        candidate_id: int,
    ) -> ReplayDecision:
        """Replay an already queried candidate at exactly 90 digits."""


@dataclass(frozen=True)
class ProposalSummary:
    """Already constructed continuous split-A proposal.

    ``p`` and ``nu`` deliberately need not lie on the finite bank grids.  The
    proposal is a continuous numerator explanation, not a bank candidate.
    """

    phi: float
    p: float
    nu: float
    replay_admissible: bool
    replay_precision_decimal_digits: int = 90

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.phi, self.p, self.nu)):
            raise ValueError("proposal coordinates must be finite")
        if not -0.4 <= self.phi <= 0.4:
            raise ValueError("proposal phi must belong to the frozen shell")
        if not 0.15 <= self.p <= 0.30:
            raise ValueError("proposal p must belong to the frozen shell")
        if not 0.80 <= self.nu <= 1.20:
            raise ValueError("proposal nu must belong to the frozen shell")
        if self.replay_precision_decimal_digits != 90:
            raise ValueError("proposal replay must use exactly 90 digits")


@dataclass(frozen=True)
class SearchRules:
    """Frozen B0 search rules, allowing only stricter test-time caps."""

    alpha: float = 0.077
    maximum_unique_queries: int = 320
    maximum_high_precision_replays: int = 48
    maximum_accepted_witnesses: int = 16
    maximum_anchors: int = 4
    wall_seconds_cap: float = 900.0
    near_shell_stop_fraction: float = 0.98
    improvement_tolerance_fraction: float = 1.0e-4
    resolution_fractions: tuple[float, ...] = (
        0.10,
        0.20,
        0.30,
        0.40,
        0.50,
    )

    def __post_init__(self) -> None:
        if self.alpha != 0.077:
            raise ValueError("B0 primary alpha is frozen at 0.077")
        integer_caps = (
            ("maximum_unique_queries", self.maximum_unique_queries, 320),
            (
                "maximum_high_precision_replays",
                self.maximum_high_precision_replays,
                48,
            ),
            (
                "maximum_accepted_witnesses",
                self.maximum_accepted_witnesses,
                16,
            ),
            ("maximum_anchors", self.maximum_anchors, 4),
        )
        for name, value, frozen_maximum in integer_caps:
            if not 1 <= int(value) <= frozen_maximum:
                raise ValueError(f"{name} must be in [1,{frozen_maximum}]")
        if not 0.0 < self.wall_seconds_cap <= 900.0:
            raise ValueError("wall_seconds_cap must be in (0,900]")
        if self.near_shell_stop_fraction != 0.98:
            raise ValueError("near-shell stop fraction is frozen at 0.98")
        if self.improvement_tolerance_fraction != 1.0e-4:
            raise ValueError(
                "improvement tolerance fraction is frozen at 1e-4"
            )
        if self.resolution_fractions != (0.10, 0.20, 0.30, 0.40, 0.50):
            raise ValueError("B0 resolution fractions are frozen")
