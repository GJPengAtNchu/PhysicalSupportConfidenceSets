"""Construction of one frozen scientific case without oracle enumeration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..raw_bank_adapter import FiniteBankEProcessPort, FiniteBankReplayPort
from ..public_bank.bank import PublicBank, role_bank
from ..public_bank.geometry import ProjectiveOrientationMetric
from ..query_replay.scenario_replay import ScenarioHighPrecisionReplay
from ..runtime.config import Scenario
from ..runtime.science import ScientificRun, build_scientific_run
from ..frozen_policy.evidence import PublicCandidate, PublicCaseManifest

from .constants import Condition
from .util import hash_array


@dataclass
class CaseBundle:
    case_id: str
    condition: Condition
    replicate: int
    data_seed: int
    split_seed: int
    run: ScientificRun
    bank: PublicBank
    metric: ProjectiveOrientationMetric
    d_shell: float
    manifest: PublicCaseManifest
    eprocess: FiniteBankEProcessPort
    replay: FiniteBankReplayPort
    data_sha256: str


def construct_case(
    condition: Condition,
    replicate: int,
    data_seed: int,
    split_seed: int,
    *,
    case_id: str | None = None,
) -> CaseBundle:
    identity = case_id or f"{condition.name}/SEED_{replicate:02d}"
    scenario = Scenario(
        name=condition.name,
        sample_size=condition.sample_size,
        collision_scale=condition.scale,
        truth_nu=condition.truth_nu,
        oracle_wall_seconds=condition.oracle_cap_seconds,
        bank_template=condition.bank_template,
        candidate_id=condition.name,
    )
    run = build_scientific_run(
        scenario, data_seed=int(data_seed), split_seed=int(split_seed)
    )
    bank = role_bank(condition.bank_template, condition.truth_nu)
    if len(bank) != condition.candidate_count:
        raise RuntimeError("frozen bank count mismatch")
    if not bank.contains_truth(condition.truth_nu):
        raise RuntimeError("frozen bank does not contain declared truth")
    metric = ProjectiveOrientationMetric(condition.scale)
    phis = tuple(float(value) for value in bank.phi_grid_text)
    d_shell = metric.grid_shell_diameter(phis)
    public_candidates = tuple(
        PublicCandidate(
            candidate_id=str(candidate.candidate_id),
            phi=candidate.phi,
            nuisance=(candidate.p, candidate.nu),
        )
        for candidate in bank.candidates
    )
    proposal_raw = tuple(float(value) for value in run.proposal.raw)
    manifest = PublicCaseManifest(
        case_id=identity,
        role=condition.name,
        cell=condition.name,
        pilot=f"SEED_{replicate:02d}",
        scale=condition.scale,
        target_raw=proposal_raw,
        candidates=public_candidates,
        d_shell=d_shell,
        result_path=Path("__PRIMARY_ORACLE_NOT_OPEN__"),
        candidates_path=Path("__PRIMARY_ORACLE_NOT_OPEN__"),
    )
    process = FiniteBankEProcessPort(run.eprocess, bank)
    hp = ScenarioHighPrecisionReplay(
        run.split.evaluation,
        run.eprocess.checkpoints,
        run.proposal.x,
        scenario_s=condition.scale,
    )
    replay = FiniteBankReplayPort(hp, bank)
    return CaseBundle(
        case_id=identity,
        condition=condition,
        replicate=replicate,
        data_seed=int(data_seed),
        split_seed=int(split_seed),
        run=run,
        bank=bank,
        metric=metric,
        d_shell=d_shell,
        manifest=manifest,
        eprocess=process,
        replay=replay,
        data_sha256=hash_array(run.observations),
    )


def proposal_record(bundle: CaseBundle) -> dict[str, Any]:
    value = bundle.run.proposal.to_json()
    value.update(
        {
            "construction": "REPAIRED_SAFE_CONTINUOUS_SPLIT_A_OPERATIONAL_PROPOSAL",
            "shared_bounded_optimizer_adapter": "SafeBoundedObjective",
            "may_lie_off_bank": True,
        }
    )
    return value


def data_manifest(bundle: CaseBundle) -> dict[str, Any]:
    return {
        "case_id": bundle.case_id,
        "condition": bundle.condition.name,
        "replicate": bundle.replicate,
        "data_seed": bundle.data_seed,
        "split_seed": bundle.split_seed,
        "N": bundle.condition.sample_size,
        "s": bundle.condition.scale,
        "phi_truth": 0.0,
        "p_truth": 0.20,
        "nu_truth": bundle.condition.truth_nu,
        "bank_template": bundle.condition.bank_template,
        "candidate_count": len(bundle.bank),
        "data_sha256": bundle.data_sha256,
        "proposal": proposal_record(bundle),
    }
