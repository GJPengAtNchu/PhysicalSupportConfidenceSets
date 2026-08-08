"""Frozen scientific core for the LA1.3-ARA-B2-D2 application.

This package is deliberately independent of the locked B1/B1.1 and unsealed
D1 source trees.  It reuses the verified split-likelihood-ratio semantics for
the frozen persistent-plus-optional four-region application.
"""

from .bank import CandidateBank, build_candidate_bank
from .geometry import ApplicationGeometry, build_geometry
from .scoring import (
    CalibrationLikelihoodCache,
    CandidateScoreTable,
    DeploymentLikelihoodCache,
    score_candidate_bank,
)

__all__ = [
    "ApplicationGeometry",
    "CalibrationLikelihoodCache",
    "CandidateBank",
    "CandidateScoreTable",
    "DeploymentLikelihoodCache",
    "build_candidate_bank",
    "build_geometry",
    "score_candidate_bank",
]
