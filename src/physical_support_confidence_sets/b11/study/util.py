"""Deterministic serialization, hashing, and seed-embargo helpers."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any, Iterable

import numpy as np


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_array(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(canonical_json(list(array.shape)).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, values: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        for value in values:
            stream.write(canonical_json(value) + "\n")


def write_jsonl(path: Path, values: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(canonical_json(value) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def read_development_seed_sections(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    marker = b'  "primary": {'
    parts: list[bytes] = []
    consumed = 0
    with path.open("rb") as stream:
        while True:
            line = stream.readline()
            if not line:
                break
            marker_at = line.find(marker)
            if marker_at >= 0:
                parts.append(line[:marker_at])
                consumed += marker_at
                break
            parts.append(line)
            consumed += len(line)
    prefix = b"".join(parts).rstrip()
    if not prefix:
        raise ValueError("primary seed marker is absent")
    if not prefix.endswith(b","):
        raise ValueError("seed prefix is not a JSON object prefix")
    partial = prefix[:-1] + b"\n}"
    record = json.loads(partial)
    audit = {
        "bytes_consumed_semantically": len(partial),
        "file_size": path.stat().st_size,
        "primary_semantically_opened": False,
        "marker_offset": consumed,
        "cryptographic_file_sha256": sha256_file(path),
    }
    return record, audit


def open_primary_seeds_after_freeze(
    path: Path, freeze_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if not freeze.get("verified") or not freeze.get("independent_verification"):
        raise RuntimeError("primary seed opening requires verified code freeze")
    record = json.loads(path.read_text(encoding="utf-8"))
    primary = record.get("primary")
    if not isinstance(primary, dict):
        raise ValueError("primary seed section is absent")
    return primary, {
        "primary_semantically_opened": True,
        "opened_after_verified_freeze": True,
        "seed_file_sha256": sha256_file(path),
    }


def environment_record() -> dict[str, Any]:
    import scipy

    return {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "pid": os.getpid(),
        "network_used": False,
        "execution_mode": "READ_ONLY_OFFLINE_SCIENTIFIC_INPUTS_LOCAL_ARTIFACT_WRITES",
    }
