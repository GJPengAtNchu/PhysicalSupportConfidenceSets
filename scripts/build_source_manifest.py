#!/usr/bin/env python3
"""Build the publication source/provenance manifest for every committed file."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


FIELDS = (
    "public_path",
    "public_sha256",
    "source_reference",
    "source_sha256",
    "scientific_role",
    "nonbehavioral_cleanup",
)

EXTERNAL_PUBLICATION_INPUTS = {
    "docs/supplement.pdf": {
        "source_reference": (
            "Physical_Support_Confidence_Sets_Source_V1/supplement.pdf"
        ),
        "source_sha256": (
            "1ba1fc685e4b042324392cd2539523db3f5e3741a9ddbda159b1e2b51349b57f"
        ),
        "cleanup": "none; byte-identical manuscript supplement",
    },
    (
        "artifacts/canonical_paper_export/b11_global/figure_data/"
        "controller_results.csv"
    ): {
        "source_reference": (
            "B11_GLOBAL_FINAL_EVIDENCE.zip::read_only_b1/controller_results.csv"
        ),
        "source_sha256": (
            "55384e4e8d52f0f882de70cb3b70334812f4c78e3114041aabf5130d049884d3"
        ),
        "cleanup": (
            "line-ending normalization only (CRLF to LF); 324 saved data rows "
            "and all scientific values unchanged"
        ),
    },
    "artifacts/canonical_paper_export/paper/figure_sources/figure1/"
    "conceptual_pipeline_panel_a.tex": {
        "source_reference": (
            "Physical_Support_Confidence_Sets_Source_V1 working source::"
            "conceptual_pipeline_panel_a.tex"
        ),
        "source_sha256": (
            "77baa1545e5606a0ed6eb131248b9e985d9df5722a0a8917fb986ed6723cc96f"
        ),
        "cleanup": "line-ending/trailing-newline normalization only",
    },
    "artifacts/canonical_paper_export/paper/figure_sources/figure1/"
    "conceptual_pipeline_panel_b.tex": {
        "source_reference": (
            "Physical_Support_Confidence_Sets_Source_V1 working source::"
            "conceptual_pipeline_panel_b.tex"
        ),
        "source_sha256": (
            "b4694a3b1086581b4b4888a92b20da44a87a1ecc658030baa6f1512ba906e8c0"
        ),
        "cleanup": "line-ending/trailing-newline normalization only",
    },
    "artifacts/canonical_paper_export/paper/figure_sources/figure1/"
    "conceptual_pipeline_panel_c.tex": {
        "source_reference": (
            "Physical_Support_Confidence_Sets_Source_V1 working source::"
            "conceptual_pipeline_panel_c.tex"
        ),
        "source_sha256": (
            "17195344c1680b40e1442443c61c07131b0f8649d208989f9d1c1d5547b8e695"
        ),
        "cleanup": "line-ending/trailing-newline normalization only",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def role(path: str) -> str:
    if path.startswith("src/physical_support_confidence_sets/b11/"):
        return "B1.1 recovered scientific implementation"
    if path.startswith("src/physical_support_confidence_sets/formal_b2/"):
        return "Formal B2 byte-frozen D2.3 scientific core"
    if path.startswith("src/physical_support_confidence_sets/original_numerical/"):
        return "theorem-native numerical illustration; HOLD_NUMERICAL_EVIDENCE"
    if path.startswith("configs/"):
        return "frozen configuration, seed, case order, gate, or freeze provenance"
    if path.startswith("artifacts/canonical_paper_export/"):
        return "immutable compact canonical paper export"
    if path.startswith("docs/frozen_semantics/"):
        return "M0 frozen semantic anchor"
    if path.startswith("tests/"):
        return "publication invariant test"
    if path.startswith("scripts/"):
        return "publication reproduction/validation wrapper"
    if path.startswith("examples/"):
        return "representative non-adjudicative output"
    return "publication documentation or package metadata"


def b11_origin(relative: str) -> str | None:
    prefix = "src/physical_support_confidence_sets/b11/"
    if not relative.startswith(prefix):
        return None
    tail = relative[len(prefix) :]
    mappings = (
        ("scientific_core/", "src/"),
        ("public_bank/", "b0_public/"),
        ("runtime/", "b0_runtime/"),
        ("query_replay/scenario_replay.py", "b0_query_worker/scenario_replay.py"),
        ("frozen_policy/", "frozen_policy/"),
        ("study/", "b1/"),
        ("raw_bank_adapter.py", "b01_raw_bank_adapter.py"),
    )
    for public_prefix, source_prefix in mappings:
        if tail == public_prefix or tail.startswith(public_prefix):
            suffix = tail[len(public_prefix) :] if public_prefix.endswith("/") else ""
            return source_prefix + suffix
    return None


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    b1_freeze = json.loads(
        (repository / "configs/b11_global/B1_CODE_FREEZE.json").read_text(
            encoding="utf-8"
        )
    )
    b1_hashes = {
        key: value["sha256"] for key, value in b1_freeze["tracked_files"].items()
    }
    b2_freeze = json.loads(
        (repository / "configs/formal_b2/b2f01_code_freeze.json").read_text(
            encoding="utf-8"
        )
    )
    b2_hashes = b2_freeze["successor_d2d23_core_file_sha256"]

    manifest_path = repository / "docs/SOURCE_MANIFEST.csv"
    files = sorted(
        path
        for path in repository.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and ".venv" not in path.parts
        and "build" not in path.parts
        and ".pytest_cache" not in path.parts
        and not any(part.endswith(".egg-info") for part in path.parts)
        and "__pycache__" not in path.parts
        and not path.name.endswith((".pyc", ".pyo"))
    )
    if manifest_path not in files:
        files.append(manifest_path)
        files.sort()
    rows: list[dict[str, str]] = []
    for path in files:
        relative = path.relative_to(repository).as_posix()
        if relative == "docs/SOURCE_MANIFEST.csv":
            rows.append(
                {
                    "public_path": relative,
                    "public_sha256": "SELF_REFERENTIAL_NOT_RECORDED",
                    "source_reference": "generated by scripts/build_source_manifest.py",
                    "source_sha256": "SELF_REFERENTIAL_NOT_RECORDED",
                    "scientific_role": "publication source provenance index",
                    "nonbehavioral_cleanup": "self-row intentionally has no recursive digest",
                }
            )
            continue

        public_hash = sha256(path)
        source_reference = "PUBLICATION_RELEASE_V1"
        source_hash = public_hash
        cleanup = "new publication file"

        original_b11 = b11_origin(relative)
        if original_b11 is not None and original_b11 in b1_hashes:
            source_reference = f"la1_3_ara_b11/locked_b1_source/{original_b11}"
            source_hash = b1_hashes[original_b11]
            cleanup = (
                "none; byte-identical relocation"
                if public_hash == source_hash
                else "publication namespace/import or nonportable historical-path cleanup only"
            )
        elif relative.startswith("src/physical_support_confidence_sets/formal_b2/"):
            name = relative.rsplit("/", 1)[-1]
            key = f"b2d2/{name}"
            source_reference = f"la1_3_ara_b2f01/successor_source/{key}"
            source_hash = b2_hashes[key]
            cleanup = "none; byte-identical relocation"
        elif relative.startswith("src/physical_support_confidence_sets/original_numerical/"):
            name = relative.rsplit("/", 1)[-1]
            source_reference = f"ORIGINAL_THREE_GATE_EXPERIMENT_EVIDENCE.zip::simulation/{name}"
            cleanup = "none; archive member verified byte-identical"
        elif relative in EXTERNAL_PUBLICATION_INPUTS:
            external = EXTERNAL_PUBLICATION_INPUTS[relative]
            source_reference = external["source_reference"]
            source_hash = external["source_sha256"]
            cleanup = external["cleanup"]
        elif relative == (
            "artifacts/canonical_paper_export/provenance/checksums.sha256"
        ):
            source_reference = (
                "Physical_Support_Confidence_Sets_Source_V1.zip::"
                "Physical_Support_Confidence_Sets_Source_V1/"
                "canonical_paper_export/provenance/checksums.sha256"
            )
            source_hash = (
                "3845204e78236164afac879c3ed9023fe95e1552393e5fa5278635a5f631ae88"
            )
            cleanup = (
                "original 70-entry tree preserved; four publication-facing "
                "inputs appended to form the 74-entry release tree"
            )
        elif relative.startswith("artifacts/canonical_paper_export/"):
            tail = relative[len("artifacts/canonical_paper_export/") :]
            source_reference = (
                "Physical_Support_Confidence_Sets_Source_V1.zip::"
                f"Physical_Support_Confidence_Sets_Source_V1/canonical_paper_export/{tail}"
            )
            cleanup = "none; canonical export member"
        elif relative.startswith("docs/frozen_semantics/"):
            name = relative.rsplit("/", 1)[-1]
            source_reference = (
                "Physical_Support_Confidence_Sets_Source_V1.zip::"
                f"Physical_Support_Confidence_Sets_Source_V1/m0_freeze/{name}"
            )
            cleanup = "none; frozen manuscript semantic anchor"
        elif relative.startswith("configs/original_numerical/"):
            name = relative.rsplit("/", 1)[-1]
            source_reference = f"ORIGINAL_THREE_GATE_EXPERIMENT_EVIDENCE.zip::{name}"
            cleanup = "none; archive member verified byte-identical"
        elif relative.startswith("configs/b11_global/"):
            name = relative.rsplit("/", 1)[-1]
            source_reference = f"la1_3_ara_b11 frozen input/provenance::{name}"
            cleanup = "none; frozen input/provenance copy"
        elif relative.startswith("configs/formal_b2/"):
            name = relative.rsplit("/", 1)[-1]
            source_reference = f"la1_3_ara_b2f01 frozen input/provenance::{name}"
            cleanup = "none; frozen input/provenance copy"

        rows.append(
            {
                "public_path": relative,
                "public_sha256": public_hash,
                "source_reference": source_reference,
                "source_sha256": source_hash,
                "scientific_role": role(relative),
                "nonbehavioral_cleanup": cleanup,
            }
        )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} source-manifest rows to {manifest_path}")


if __name__ == "__main__":
    main()
