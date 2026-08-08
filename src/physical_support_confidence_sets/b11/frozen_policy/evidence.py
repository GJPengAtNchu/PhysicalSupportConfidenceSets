"""Restricted readers for immutable stored B0.1 evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .geometry import canonical_diameter, shell_diameter
from .sealed_query import CandidateStatus


ALPHAS = (Decimal("0.025"), Decimal("0.077"), Decimal("0.15"))
PROFILE_PARAMETERS = {
    "RISK_CONSERVATIVE": (Decimal("0.025"), 0.40, 0.50),
    "BALANCED": (Decimal("0.077"), 0.35, 0.60),
    "RESOLUTION_FAVORING": (Decimal("0.15"), 0.25, 0.40),
}


@dataclass(frozen=True)
class PublicCandidate:
    candidate_id: str
    phi: float
    nuisance: tuple[float, float]


@dataclass(frozen=True)
class PublicCaseManifest:
    case_id: str
    role: str
    cell: str
    pilot: str
    scale: float
    target_raw: tuple[float, float, float]
    candidates: tuple[PublicCandidate, ...]
    d_shell: float
    result_path: Path
    candidates_path: Path


@dataclass(frozen=True)
class StoredScoreRow:
    candidate_id: str
    log_e: tuple[float, ...]
    high_precision_log_e: tuple[float, ...] | None

    def status(self, alpha: Decimal) -> CandidateStatus:
        values = (
            self.high_precision_log_e
            if self.high_precision_log_e is not None
            else self.log_e
        )
        return (
            CandidateStatus.ADMISSIBLE
            if max(values) <= math.log(1.0 / float(alpha))
            else CandidateStatus.REJECTED
        )


class StoredScoreVault:
    """Private score records, intentionally separate from public geometry."""

    __slots__ = ("__rows",)

    def __init__(self, rows: tuple[StoredScoreRow, ...]):
        object.__setattr__(self, "_StoredScoreVault__rows", rows)

    def status_table(self, alpha: Decimal) -> dict[str, CandidateStatus]:
        rows = object.__getattribute__(self, "_StoredScoreVault__rows")
        return {row.candidate_id: row.status(alpha) for row in rows}

    def __dir__(self) -> list[str]:
        return ["status_table"]


@dataclass(frozen=True)
class OpenedReference:
    d_bank: float
    endpoints: tuple[Any, ...]
    survivor_count: int
    label: str
    stored_metric_match: bool
    stored_max_mismatch: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_json_object(text: str, key: str) -> dict[str, Any]:
    marker = json.dumps(key) + ":"
    start = text.find(marker)
    if start < 0:
        raise KeyError(f"missing restricted header key {key!r}")
    cursor = start + len(marker)
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    if cursor >= len(text) or text[cursor] != "{":
        raise ValueError(f"restricted header key {key!r} is not an object")
    depth = 0
    in_string = False
    escaped = False
    for end in range(cursor, len(text)):
        char = text[end]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[cursor : end + 1])
    raise ValueError(f"unterminated restricted header object {key!r}")


def _restricted_target_raw(result_path: Path) -> tuple[float, float, float]:
    """Return only the permitted target coordinates, never an oracle field."""

    text = result_path.read_text(encoding="utf-8")
    record = _extract_json_object(text, "proposal")
    raw = tuple(float(value) for value in record["raw"])
    if len(raw) != 3:
        raise ValueError(f"invalid target coordinates in {result_path}")
    return raw  # type: ignore[return-value]


def discover_stored_cases(root: Path) -> list[tuple[PublicCaseManifest, StoredScoreVault]]:
    cases: list[tuple[PublicCaseManifest, StoredScoreVault]] = []
    paths = sorted(root.glob("scenario_calibration/*/*/PILOT_*/oracle/result.json"))
    for result_path in paths:
        pilot = result_path.parents[1].name
        cell = result_path.parents[2].name
        role = result_path.parents[3].name
        case_id = f"{role}/{cell}/{pilot}"
        job = json.loads((result_path.parents[1] / "job.json").read_text(encoding="utf-8"))
        scale = float(job["scenario"]["s"])
        candidates_path = result_path.parent / "candidates.jsonl"
        public_rows: list[PublicCandidate] = []
        private_rows: list[StoredScoreRow] = []
        for line in candidates_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            candidate_id = str(int(row["candidate_id"]))
            raw = tuple(float(value) for value in row["raw"])
            high_precision = row.get("high_precision")
            public_rows.append(
                PublicCandidate(
                    candidate_id=candidate_id,
                    phi=raw[0],
                    nuisance=(raw[1], raw[2]),
                )
            )
            private_rows.append(
                StoredScoreRow(
                    candidate_id=candidate_id,
                    log_e=tuple(float(value) for value in row["log_e"]),
                    high_precision_log_e=(
                        tuple(float(value) for value in high_precision["log_e"])
                        if high_precision is not None
                        else None
                    ),
                )
            )
        public_rows.sort(key=lambda item: int(item.candidate_id))
        private_rows.sort(key=lambda item: int(item.candidate_id))
        ids = [item.candidate_id for item in public_rows]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate candidate ID in {case_id}")
        if ids != [str(index) for index in range(len(ids))]:
            raise ValueError(f"noncanonical candidate IDs in {case_id}")
        target_raw = _restricted_target_raw(result_path)
        manifest = PublicCaseManifest(
            case_id=case_id,
            role=role,
            cell=cell,
            pilot=pilot,
            scale=scale,
            target_raw=target_raw,
            candidates=tuple(public_rows),
            d_shell=shell_diameter(scale, [item.phi for item in public_rows]),
            result_path=result_path,
            candidates_path=candidates_path,
        )
        cases.append((manifest, StoredScoreVault(tuple(private_rows))))
    cases.sort(key=lambda pair: _case_sort_key(pair[0].case_id))
    return cases


def _case_sort_key(case_id: str) -> tuple[int, int, int]:
    role, cell, pilot = case_id.split("/")
    role_order = {"FULL": 0, "SECTOR": 1, "RESOLVED": 2}
    return role_order[role], int(cell[1:]), int(pilot.split("_")[1])


def open_reference_after_seal(
    manifest: PublicCaseManifest,
    vault: StoredScoreVault,
    profile: str,
    trace_hash: str,
    sealed_hashes: Mapping[tuple[str, str], str],
) -> OpenedReference:
    """Open and verify the exact stored finite reference after trace sealing."""

    key = (manifest.case_id, profile)
    if not trace_hash or sealed_hashes.get(key) != trace_hash:
        raise RuntimeError(f"reference opening before matching trace seal: {key}")
    alpha, delta_f_fraction, delta_s_fraction = PROFILE_PARAMETERS[profile]
    statuses = vault.status_table(alpha)
    survivor_ids = {
        candidate_id
        for candidate_id, status in statuses.items()
        if status is CandidateStatus.ADMISSIBLE
    }
    points: list[tuple[Any, float]] = [("PROPOSAL", manifest.target_raw[0])]
    seen = {manifest.target_raw[0]}
    for candidate in manifest.candidates:
        if candidate.candidate_id not in survivor_ids or candidate.phi in seen:
            continue
        seen.add(candidate.phi)
        points.append((int(candidate.candidate_id), candidate.phi))
    d_bank, endpoints = canonical_diameter(manifest.scale, points)
    delta_f = delta_f_fraction * manifest.d_shell
    delta_s = delta_s_fraction * manifest.d_shell
    if d_bank <= delta_f:
        label = "ORACLE_FINE"
    elif d_bank <= delta_s:
        label = "ORACLE_SECTOR"
    else:
        label = "ORACLE_AMBIGUOUS"

    stored_result = json.loads(manifest.result_path.read_text(encoding="utf-8"))
    selected = next(
        row
        for row in stored_result["alpha_metrics"]
        if Decimal(str(row["alpha"])) == alpha
    )
    mismatch = max(
        abs(d_bank - float(selected["d_bank"])),
        abs(d_bank / manifest.d_shell - float(selected["diameter_fraction"])),
    )
    stored_match = (
        mismatch <= 1.0e-12
        and len(survivor_ids) == int(selected["survivor_count"])
        and list(endpoints) == selected["diameter_endpoints"]
    )
    return OpenedReference(
        d_bank=d_bank,
        endpoints=endpoints,
        survivor_count=len(survivor_ids),
        label=label,
        stored_metric_match=stored_match,
        stored_max_mismatch=mismatch,
    )

