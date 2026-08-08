#!/usr/bin/env python3
"""Validate the complete publication release; exit nonzero on any mismatch."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterable


EXPECTED_ARCHIVES = {
    "B11_GLOBAL_FINAL_EVIDENCE.zip": "2095d8c17081cc9e574f5e052b2a1100864eff499610c45ef2c999905bf67c83",
    "FORMAL_B2_FINAL_EVIDENCE.zip": "89649c27c956a2ade19ea2fe16ef549b4a028d7d544fd5eeef47a1dd4bddc738",
    "ORIGINAL_THREE_GATE_EXPERIMENT_EVIDENCE.zip": "cb99fc8fda7efa3872185f0ca1460de262fdc201d2a1996182e74b47a00b8379",
    "Honest_Collision_Aware_Dictionary_Refinement_V2_SOURCE.zip": "8ab580ae47fe83455814f840b6bf32133bf074c7f388eec7f170523b3f85f872",
    "Physical_Support_Confidence_Sets_Source_V1.zip": "8b2a6888cf0b40bf874f92452bc6362365f55de6c48f7272c28ef2322f9cbe48",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(repository: Path, *arguments: str) -> None:
    print("+", sys.executable, *arguments, flush=True)
    subprocess.run([sys.executable, *arguments], cwd=repository, check=True)


def file_hashes(root: Path, *, exclude: Iterable[str] = ()) -> dict[str, str]:
    excluded = set(exclude)
    return {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in excluded
    }


def verify_archive_provenance(repository: Path) -> None:
    text = (repository / "docs/RESULT_PROVENANCE.md").read_text(encoding="utf-8")
    for name, digest in EXPECTED_ARCHIVES.items():
        assert name in text, f"missing archive provenance: {name}"
        assert digest in text, f"missing archive digest: {name}"


def verify_manifest(repository: Path) -> None:
    manifest = repository / "docs/SOURCE_MANIFEST.csv"
    with manifest.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_path = {row["public_path"]: row for row in rows}
    assert len(by_path) == len(rows), "duplicate SOURCE_MANIFEST path"
    actual = {
        path.relative_to(repository).as_posix()
        for path in repository.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and ".venv" not in path.parts
        and "build" not in path.parts
        and ".pytest_cache" not in path.parts
        and not any(part.endswith(".egg-info") for part in path.parts)
        and "__pycache__" not in path.parts
        and not path.name.endswith((".pyc", ".pyo"))
    }
    assert set(by_path) == actual, (
        f"SOURCE_MANIFEST closure mismatch: missing={sorted(actual - set(by_path))}; "
        f"extra={sorted(set(by_path) - actual)}"
    )
    for relative, row in by_path.items():
        if relative == "docs/SOURCE_MANIFEST.csv":
            assert row["public_sha256"] == "SELF_REFERENTIAL_NOT_RECORDED"
        else:
            assert sha256(repository / relative) == row["public_sha256"], relative
        assert row["source_reference"]
        assert row["source_sha256"]
        assert row["scientific_role"]


def verify_hygiene(repository: Path) -> None:
    ignored_parts = {".git", ".venv", ".pytest_cache", "__pycache__", "build"}
    prohibited_names = {".DS_Store", ".env", ".pytest_cache", "__pycache__"}
    text_suffixes = {
        ".cfg", ".csv", ".json", ".md", ".py", ".toml", ".tex", ".txt", ".yaml", ".yml"
    }
    private_tokens = (
        "C:" + "\\" + "Users\\",
        "C:" + "/" + "Users/",
        "/" + "Users/",
        "/" + "home/",
        "/" + "tmp/",
    )
    for path in repository.rglob("*"):
        if any(part in ignored_parts or part.endswith(".egg-info") for part in path.parts):
            continue
        assert path.name not in prohibited_names, f"prohibited cache/private file: {path}"
        if not path.is_file():
            continue
        assert path.suffix.lower() not in {".pyc", ".pyo", ".pem", ".key"}
        assert path.suffix.lower() != ".zip", "raw evidence archives must not be committed"
        if path.suffix.lower() in text_suffixes:
            text = path.read_text(encoding="utf-8")
            for token in private_tokens:
                assert token not in text, f"private absolute path token {token!r}: {path}"
    assert not any((repository / name).exists() for name in ("LICENSE", "LICENSE.md", "COPYING"))


def verify_canonical_semantics(repository: Path) -> None:
    root = repository / "artifacts/canonical_paper_export"
    b11 = json.loads((root / "b11_global/canonical_summary.json").read_text(encoding="utf-8"))
    formal = json.loads((root / "formal_b2/canonical_merged_summary.json").read_text(encoding="utf-8"))
    p05 = json.loads((root / "formal_b2/empty_profile_disclosure.json").read_text(encoding="utf-8"))
    original = json.loads((root / "original_numerical/canonical_summary.json").read_text(encoding="utf-8"))
    assert b11["completed_finite_bank_cases"] == 18
    assert b11["sealed_global_controller_traces"] == 54
    assert b11["safety"]["bound_denominator"] is None
    assert formal["formal_case_count"] == 15
    assert formal["completed_exact_oracle_count"] == 14
    assert formal["administrative_empty_profile_count"] == 1
    assert formal["safety"]["zero_possible_set_violations"]["denominator"] == 15
    assert formal["safety"]["zero_bound_violations"]["denominator"] == 2088
    assert formal["safety"]["zero_unsafe_outputs"]["denominator"] == 56
    assert p05["case_id"] == "FORMAL_WEAK_C_PRESENT_P05"
    assert p05["exact_profile_candidate_ids"] == []
    assert p05["oracle_map"] is None and p05["reported_physical_map"] is None
    assert p05["native_status"] == "ORACLE_EMPTY_PROFILE_INCOMPLETE"
    assert original["status"] == "HOLD_NUMERICAL_EVIDENCE"


def verify_examples(repository: Path, root: Path) -> None:
    for study, filename in (("b11", "b11.json"), ("formal-b2", "formal_b2.json")):
        first = root / "examples_1" / filename
        second = root / "examples_2" / filename
        run(repository, "scripts/run_representative_example.py", "--study", study, "--output", str(first))
        run(repository, "scripts/run_representative_example.py", "--study", study, "--output", str(second))
        assert first.read_bytes() == second.read_bytes(), f"nondeterministic example: {study}"
        payload = json.loads(first.read_text(encoding="utf-8"))
        assert payload["scientific_claim"] is False
        assert payload["candidate_count"] in {27, 216}
        assert payload["typed_output"]
        assert payload["termination"]
    formal = json.loads((root / "examples_1/formal_b2.json").read_text(encoding="utf-8"))
    assert formal["dictionary_state_count"] == 72
    assert formal["candidate_count"] == 216
    assert formal["lower_count"] <= formal["possible_count"]
    assert formal["exact_profile_count"] > 0
    assert "1e-10" in formal["floating_point_rule"]


def verify_artifact_reproduction(repository: Path, root: Path) -> None:
    table_one = root / "tables_1"
    table_two = root / "tables_2"
    run(repository, "scripts/regenerate_paper_tables.py", "--output-dir", str(table_one.relative_to(repository)))
    run(repository, "scripts/regenerate_paper_tables.py", "--output-dir", str(table_two.relative_to(repository)))
    assert file_hashes(table_one) == file_hashes(table_two)

    figure_one = root / "figures_1"
    figure_two = root / "figures_2"
    run(repository, "scripts/regenerate_paper_figures.py", "--output-dir", str(figure_one.relative_to(repository)))
    run(repository, "scripts/regenerate_paper_figures.py", "--output-dir", str(figure_two.relative_to(repository)))
    receipt_one = json.loads((figure_one / "figure_reproduction_receipt.json").read_text(encoding="utf-8"))
    receipt_two = json.loads((figure_two / "figure_reproduction_receipt.json").read_text(encoding="utf-8"))
    assert receipt_one == receipt_two
    assert len(receipt_one["outputs"]) == 10
    assert receipt_one["displayed_canonical_fields"] == json.loads(
        (repository / "artifacts/canonical_paper_export/paper/figure_generation_receipt.json").read_text(encoding="utf-8")
    )["displayed_canonical_fields"]


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    output = repository / "build/release_validation"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    verify_archive_provenance(repository)
    verify_manifest(repository)
    verify_hygiene(repository)
    verify_canonical_semantics(repository)
    run(repository, "-m", "pytest", "-q")
    verify_examples(repository, output)
    verify_artifact_reproduction(repository, output)

    subprocess.run(["git", "diff", "--check"], cwd=repository, check=True)
    subprocess.run(["git", "diff", "--cached", "--check"], cwd=repository, check=True)

    report = {
        "schema_version": "PUBLICATION_RELEASE_VALIDATION_V1",
        "status": "PASS_PUBLICATION_RELEASE_VALIDATED",
        "canonical_semantics": "exact",
        "tests": "passed",
        "representative_examples": ["b11", "formal-b2"],
        "figures_reproduced": 5,
        "figure_formats": ["PNG", "PDF"],
        "tables_reproduced": 6,
        "full_frozen_study_executed": False,
        "raw_frozen_inputs_modified": False,
    }
    report_path = output / "release_validation_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"PASS_PUBLICATION_RELEASE_VALIDATED ({report_path})")


if __name__ == "__main__":
    main()
