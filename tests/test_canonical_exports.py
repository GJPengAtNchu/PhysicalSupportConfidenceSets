from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
CANONICAL = REPOSITORY / "artifacts/canonical_paper_export"


def test_canonical_export_checksum_tree_closes() -> None:
    manifest = CANONICAL / "provenance/checksums.sha256"
    rows: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        assert name not in rows
        rows[name] = digest
    actual = {
        path.relative_to(CANONICAL).as_posix()
        for path in CANONICAL.rglob("*")
        if path.is_file() and path != manifest
    }
    assert len(rows) == 70
    assert set(rows) == actual
    for name, digest in rows.items():
        assert hashlib.sha256((CANONICAL / name).read_bytes()).hexdigest() == digest


def test_b11_canonical_counts_and_status() -> None:
    summary = json.loads((CANONICAL / "b11_global/canonical_summary.json").read_text())
    assert summary["terminal_status"] == "PASS_ARA_B11_ORACLE_AUDIT_COMPLETED_AND_B1_VALIDATED"
    assert summary["completed_finite_bank_cases"] == 18
    assert summary["sealed_global_controller_traces"] == 54
    assert summary["completed_by_condition"] == {
        "HIGH_INFORMATION_R3": 6,
        "INTERMEDIATE_INFORMATION_S3": 6,
        "LOW_INFORMATION_F0": 6,
    }
    assert summary["budget_0_75"]["outputs"] == {
        "AMBIGUOUS": 34,
        "FINE": 5,
        "SECTOR_SAFE": 15,
    }
    assert summary["safety"]["bound_denominator"] is None


def test_formal_b2_counts_denominators_and_p05_null() -> None:
    summary = json.loads((CANONICAL / "formal_b2/canonical_merged_summary.json").read_text())
    p05 = json.loads((CANONICAL / "formal_b2/empty_profile_disclosure.json").read_text())
    assert summary["terminal_status"] == "PASS_ARA_B2_FORMAL_FRESH_APPLICATION_VALIDATED"
    assert summary["formal_case_count"] == 15
    assert summary["completed_exact_oracle_count"] == 14
    assert summary["administrative_empty_profile_count"] == 1
    assert summary["coverage"]["main_oracle_coverage"]["numerator"] == 11
    assert summary["coverage"]["main_oracle_coverage"]["denominator"] == 12
    assert summary["coverage"]["control_oracle_coverage"]["numerator"] == 3
    assert summary["coverage"]["control_oracle_coverage"]["denominator"] == 3
    assert summary["safety"]["zero_possible_set_violations"]["denominator"] == 15
    assert summary["safety"]["zero_bound_violations"]["denominator"] == 2088
    assert summary["safety"]["zero_unsafe_outputs"]["denominator"] == 56
    assert summary["safety"]["control_false_D_absence"]["denominator"] == 3
    assert p05["case_id"] == "FORMAL_WEAK_C_PRESENT_P05"
    assert p05["native_status"] == "ORACLE_EMPTY_PROFILE_INCOMPLETE"
    assert p05["exact_profile_candidate_ids"] == []
    assert p05["oracle_map"] is None
    assert p05["reported_physical_map"] is None
    assert p05["truth_relative_utility_eligible"] is False
    assert p05["bound_validation_included"] is False
    assert p05["stage_a_query_count"] == 162


def test_original_numerical_status_remains_hold() -> None:
    summary = json.loads((CANONICAL / "original_numerical/canonical_summary.json").read_text())
    assert summary["status"] == "HOLD_NUMERICAL_EVIDENCE"
    assert summary["failed_frozen_criterion"]["pass"] is False

