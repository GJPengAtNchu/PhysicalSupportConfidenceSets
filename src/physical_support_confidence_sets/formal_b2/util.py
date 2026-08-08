"""Deterministic serialization, hashing, and array validation helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


def canonical_json(value: Any) -> str:
    """Return the byte-for-byte canonical JSON form inherited from B1."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
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
    """Hash dtype, shape, and C-order bytes exactly as locked B1/B1.1."""

    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(canonical_json(list(array.shape)).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def readonly_float_array(value: Any, *, ndim: int | None = None) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if ndim is not None and array.ndim != int(ndim):
        raise ValueError(f"array must have dimension {int(ndim)}")
    if not np.all(np.isfinite(array)):
        raise ValueError("array must contain only finite values")
    result = np.ascontiguousarray(array).copy()
    result.setflags(write=False)
    return result
