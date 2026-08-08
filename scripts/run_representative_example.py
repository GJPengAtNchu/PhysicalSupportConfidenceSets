#!/usr/bin/env python3
"""Run one deterministic, non-adjudicative publication smoke example."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

import numpy as np


def _write(payload: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output is None:
        print(text, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8", newline="\n")


def run_b11() -> dict[str, Any]:
    """Exercise the frozen B1.1 controller on a declared synthetic status vault."""

    from physical_support_confidence_sets.b11.frozen_policy.ara_controller import (
        AEBFineSeekingController,
        replay_budget,
    )
    from physical_support_confidence_sets.b11.frozen_policy.evidence import (
        PublicCandidate,
        PublicCaseManifest,
    )
    from physical_support_confidence_sets.b11.frozen_policy.sealed_query import (
        CandidateStatus,
        PrivateStoredStatusBackend,
    )

    candidates: list[PublicCandidate] = []
    candidate_id = 0
    for phi in (-0.4, 0.0, 0.4):
        for p in (0.19, 0.20, 0.21):
            for nu in (0.75, 0.80, 0.85):
                candidates.append(PublicCandidate(str(candidate_id), phi, (p, nu)))
                candidate_id += 1
    manifest = PublicCaseManifest(
        case_id="PUBLICATION_SMOKE/SEED_00",
        role="PUBLICATION_SMOKE",
        cell="PUBLICATION_SMOKE",
        pilot="SEED_00",
        scale=0.5,
        target_raw=(0.01, 0.20, 0.80),
        candidates=tuple(candidates),
        d_shell=0.5,
        result_path=Path("__NO_ORACLE__"),
        candidates_path=Path("__NO_ORACLE__"),
    )
    statuses = {
        row.candidate_id: (
            CandidateStatus.ADMISSIBLE
            if row.phi == 0.0
            else CandidateStatus.REJECTED
        )
        for row in manifest.candidates
    }
    backend = PrivateStoredStatusBackend(tuple(statuses), statuses)
    trace = AEBFineSeekingController(manifest, "BALANCED").run_maximal(
        backend.capability()
    )
    seal = trace.seal_trace()
    replay = replay_budget(trace, 1.0)
    return {
        "schema_version": "PUBLICATION_B11_CONTROLLER_SMOKE_V1",
        "scientific_claim": False,
        "study": "B1.1 global finite-bank controller",
        "status_source": "declared deterministic synthetic vault; scorer not run",
        "candidate_count": len(candidates),
        "proposal_anchor_in_possible_geometry": True,
        "trace_sha256": seal.trace_sha256,
        "logical_query_count": replay["queries"],
        "lower_diameter": replay["lower"],
        "possible_diameter": replay["upper"],
        "typed_output": replay["output"],
        "termination": "MAXIMAL_TRACE_SEALED",
    }


def run_formal_b2() -> dict[str, Any]:
    """Exercise the actual D25 scorer, bank, controller, and projections."""

    from physical_support_confidence_sets.formal_b2.bank import build_candidate_bank
    from physical_support_confidence_sets.formal_b2.constants import ALPHA
    from physical_support_confidence_sets.formal_b2.controller import (
        PersistentOptionalAEBMapController,
        QueryReceipt,
        SealedQueryCapability,
    )
    from physical_support_confidence_sets.formal_b2.data import (
        generate_pilot_data,
        split_pilot_data,
    )
    from physical_support_confidence_sets.formal_b2.geometry import build_geometry
    from physical_support_confidence_sets.formal_b2.projection import (
        exact_oracle_projection,
        projection_payload,
    )
    from physical_support_confidence_sets.formal_b2.scoring import (
        CalibrationLikelihoodCache,
        DeploymentLikelihoodCache,
        score_candidate_bank,
    )

    # These deliberately tiny sizes make this a smoke test, not a formal case.
    geometry = build_geometry(0.085)
    bank = build_candidate_bank(geometry)
    public = bank.public_candidates()
    data = generate_pilot_data(
        bank,
        "WEAK_C_PRESENT",
        calibration_size=32,
        deployment_size=32,
        tau_b=0.80,
        tau_c=0.10,
        tau_d_beta=1.00,
        data_seed=2026080801,
    )
    splits = split_pilot_data(data, split_seed=9026080801)
    calibration = CalibrationLikelihoodCache.from_bank(bank)
    deployment = DeploymentLikelihoodCache.from_bank(
        bank, tau_b=0.80, tau_c=0.10, tau_d_beta=1.00
    )
    scores = score_candidate_bank(bank, splits, calibration, deployment, alpha=ALPHA)

    def query(candidate_id: int, reasons: tuple[str, ...]) -> QueryReceipt:
        index = candidate_id - 1
        margin = float(scores.maximum_rejection_margin[index])
        if abs(margin) <= 1.0e-10:
            status = "INDETERMINATE"
        else:
            status = "ADMISSIBLE" if bool(scores.survives_all_checkpoints[index]) else "REJECTED"
        return QueryReceipt(
            candidate_id=candidate_id,
            status=status,
            margin=margin,
            precision="DOUBLE_SMOKE_ONLY",
            replay_reasons=tuple(reasons),
            error_envelope=0.0,
        )

    proposal_id = scores.proposal.deployment_explanation_index + 1
    controller = PersistentOptionalAEBMapController(
        public,
        pilot_id="PUBLICATION_SMOKE/SEED_00",
        proposal_candidate_id=proposal_id,
        calibration_proposal_dictionary_index=(
            scores.proposal.calibration_dictionary_index
        ),
    )
    trace = controller.run(SealedQueryCapability(query))
    exact_ids = tuple(
        index + 1
        for index, survives in enumerate(scores.survives_all_checkpoints)
        if bool(survives)
    )
    exact = exact_oracle_projection(public, exact_ids)
    return {
        "schema_version": "PUBLICATION_FORMAL_B2_SCIENTIFIC_SMOKE_V1",
        "scientific_claim": False,
        "study": "Formal B2 D25 finite-bank implementation",
        "seed": {"data": 2026080801, "split": 9026080801},
        "smoke_sample_sizes": {"calibration": 32, "deployment": 32},
        "dictionary_state_count": len(bank.dictionary_states),
        "candidate_count": len(public),
        "proposal_candidate_id": proposal_id,
        "calibration_proposal_dictionary_index": (
            scores.proposal.calibration_dictionary_index
        ),
        "score_checkpoint_count": len(scores.joint_checkpoints),
        "exact_profile_count": len(exact_ids),
        "exact_projection": projection_payload(exact),
        "logical_query_count": len(trace.rows),
        "query_cap": trace.budget_cap,
        "lower_count": trace.terminal_global_explanation_bounds[
            "lower_explanation_count"
        ],
        "possible_count": trace.terminal_global_explanation_bounds[
            "upper_explanation_count"
        ],
        "typed_output": trace.terminal_map,
        "global_summary": trace.terminal_global_summary,
        "termination": trace.stop_reason,
        "trace_sha256": trace.seal.trace_sha256 if trace.seal else None,
        "floating_point_rule": (
            "double smoke status; |margin| <= 1e-10 is retained as INDETERMINATE; "
            "no 90-decimal claim is made"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", choices=("b11", "formal-b2"), required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run_b11() if args.study == "b11" else run_formal_b2()
    _write(payload, args.output)


if __name__ == "__main__":
    main()
