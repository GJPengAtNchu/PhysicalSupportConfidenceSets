"""Construction of one B0.1 dataset and its repaired split-A proposal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..scientific_core.eprocess_3d import EProcess3D
from ..scientific_core.generator import SplitSample, sample_latent, split_sample
from ..scientific_core.mixture import ExactMixtureFamily, VariableMixtureCache
from ..scientific_core.proposal import ProposalResult, construct_proposal

from .config import Scenario


@dataclass(frozen=True)
class ScientificRun:
    """Private run state; never passed into the ARA search module."""

    observations: np.ndarray
    split: SplitSample
    family: ExactMixtureFamily
    cache_a: VariableMixtureCache
    cache_b: VariableMixtureCache
    proposal: ProposalResult
    eprocess: EProcess3D


def build_scientific_run(
    scenario: Scenario,
    *,
    data_seed: int,
    split_seed: int,
) -> ScientificRun:
    """Generate, split, propose continuously, then freeze the split-B kernel."""
    observations = sample_latent(
        scenario.sample_size,
        int(data_seed),
        p=0.20,
        nu=scenario.truth_nu,
        phi=0.0,
        s=scenario.collision_scale,
    )
    split = split_sample(observations, int(split_seed))
    family = ExactMixtureFamily.from_parameters(scenario.collision_scale)
    cache_a = family.cache(split.proposal)
    cache_b = family.cache(split.evaluation)
    proposal = construct_proposal(cache_a)
    eprocess = EProcess3D.from_evaluation(cache_b, proposal.x)
    if not eprocess.survives(proposal.x):
        raise ArithmeticError("the split-A proposal is not its own admissible numerator")
    return ScientificRun(
        observations=observations,
        split=split,
        family=family,
        cache_a=cache_a,
        cache_b=cache_b,
        proposal=proposal,
        eprocess=eprocess,
    )


def proposal_public_record(proposal: ProposalResult) -> dict[str, Any]:
    """Return the public proposal summary permitted at the ARA boundary."""
    record = proposal.to_json()
    record["construction"] = (
        "REPAIRED_SAFE_CONTINUOUS_SPLIT_A_OPERATIONAL_PROPOSAL"
    )
    record["shared_bounded_optimizer_adapter"] = "SafeBoundedObjective"
    record["may_lie_off_bank"] = True
    return record
