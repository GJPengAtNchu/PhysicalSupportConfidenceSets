"""Public, score-free types for the frozen B0 finite candidate library.

This package intentionally contains no data generator, likelihood evaluator,
oracle enumerator, admissibility mask, or regime classifier.  It is the only
project package that :mod:`b0_ara` may import.
"""

from .bank import (
    NU_GRID_TEXT,
    P_GRID_TEXT,
    PHI_GRID_TEXT,
    BankCandidate,
    PublicBank,
    canonical_candidate_id,
    frozen_bank,
    role_bank,
)
from .geometry import ProjectiveOrientationMetric
from .types import (
    CandidateScore,
    ProposalSummary,
    QueryPort,
    ReplayDecision,
    SearchRules,
)

__all__ = [
    "NU_GRID_TEXT",
    "P_GRID_TEXT",
    "PHI_GRID_TEXT",
    "BankCandidate",
    "CandidateScore",
    "ProjectiveOrientationMetric",
    "ProposalSummary",
    "PublicBank",
    "QueryPort",
    "ReplayDecision",
    "SearchRules",
    "canonical_candidate_id",
    "frozen_bank",
    "role_bank",
]
