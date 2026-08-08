from __future__ import annotations

import csv
import hashlib
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]


def test_source_manifest_has_exact_public_tree_closure() -> None:
    manifest = REPOSITORY / "docs/SOURCE_MANIFEST.csv"
    with manifest.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    mapped = {row["public_path"]: row for row in rows}
    assert len(mapped) == len(rows)
    actual = {
        path.relative_to(REPOSITORY).as_posix()
        for path in REPOSITORY.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and ".venv" not in path.parts
        and "build" not in path.parts
        and ".pytest_cache" not in path.parts
        and not any(part.endswith(".egg-info") for part in path.parts)
        and "__pycache__" not in path.parts
        and not path.name.endswith((".pyc", ".pyo"))
    }
    assert set(mapped) == actual
    for relative, row in mapped.items():
        if relative == "docs/SOURCE_MANIFEST.csv":
            assert row["public_sha256"] == "SELF_REFERENTIAL_NOT_RECORDED"
        else:
            digest = hashlib.sha256((REPOSITORY / relative).read_bytes()).hexdigest()
            assert digest == row["public_sha256"]
        assert row["source_reference"] and row["source_sha256"]
