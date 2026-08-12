from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_publication_release_manifest_closes() -> None:
    manifest = json.loads(
        (REPOSITORY / "artifacts/release_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["repository_url"] == (
        "https://github.com/GJPengAtNchu/PhysicalSupportConfidenceSets"
    )
    assert manifest["terminal_statuses"] == {
        "b11": "PASS_ARA_B11_ORACLE_AUDIT_COMPLETED_AND_B1_VALIDATED",
        "formal_b2": "PASS_ARA_B2_FORMAL_FRESH_APPLICATION_VALIDATED",
        "theory_guided_numerical": "HOLD_NUMERICAL_EVIDENCE",
    }
    assert manifest["scientific_experiment_rerun"] is False
    for relative in manifest["configuration_files"]:
        assert (REPOSITORY / relative).is_file()
    for relative in manifest["canonical_result_artifacts"]:
        assert (REPOSITORY / relative).is_file()
    for relative, digest in manifest["compact_artifact_sha256"].items():
        assert sha256(REPOSITORY / relative) == digest
    assert manifest["p05_semantics"] == {
        "case_id": "FORMAL_WEAK_C_PRESENT_P05",
        "native_status": "ORACLE_EMPTY_PROFILE_INCOMPLETE",
        "exact_profile_candidate_ids": [],
        "reported_physical_map": None,
    }


def test_current_panel_renderer_uses_canonical_inputs_only() -> None:
    script = (REPOSITORY / "scripts/manuscript_panel_renderer.py").read_text(
        encoding="utf-8"
    )
    assert 'REPOSITORY_ROOT / "artifacts"' in script
    assert 'SOURCE_ROOT\n        / "canonical_paper_export"' in script
    assert "save_panel" not in script
    assert "bbox_inches" not in script
    assert "plt.subplots" in script
    assert "scientific fitting, simulation, candidate evaluation" in script
