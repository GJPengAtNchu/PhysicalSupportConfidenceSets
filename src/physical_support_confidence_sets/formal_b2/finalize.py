"""Acyclic source-freeze and deterministic evidence-bundle finalization.

The artifact checksum tree excludes itself, the evidence ZIP, and the ZIP
sidecar.  The ZIP contains the checksum-covered payload plus the checksum
manifest.  The ZIP hash is written only to the external sidecar, so no hash
depends directly or indirectly on itself.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

from .integrity import (
    IntegrityError,
    parse_sha256_manifest,
    render_sha256_manifest,
)
from .reporting import ReportingError, write_json, write_text
from .util import canonical_json, digest_json, sha256_file


CHECKSUM_MANIFEST_NAME = "checksums.sha256"
EVIDENCE_ZIP_NAME = "evidence_bundle.zip"
EVIDENCE_ZIP_SIDECAR_NAME = "evidence_bundle.zip.sha256"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_FILE_MODE = stat.S_IFREG | 0o444

REQUIRED_PREBUNDLE_FILES = (
    "FINAL_AUDIT_REPORT.md",
    "terminal_status.json",
    "environment.json",
    "input_integrity.json",
    "d0_d1_diagnostic_reproduction.json",
    "geometry_and_dictionary_invariance.json",
    "support_bank_manifest.json",
    "structural_query_feasibility.json",
    "controller_fixture_result.json",
    "controller_policy_audit.json",
    "design_ladder_results.csv",
    "design_ladder_results.jsonl",
    "development_controller_maps.csv",
    "selected_application_design.json",
    "development_oracle_maps.csv",
    "d_present_control_results.csv",
    "plugin_singleton_results.csv",
    "numerical_audit.json",
    "B2_EXECUTION_CONTRACT.md",
    "pre_pilot_source_freeze.json",
    "b2d2_design_freeze.json",
)
REQUIRED_ARTIFACT_FILES = REQUIRED_PREBUNDLE_FILES + (
    CHECKSUM_MANIFEST_NAME,
    EVIDENCE_ZIP_NAME,
    EVIDENCE_ZIP_SIDECAR_NAME,
)
REQUIRED_ARTIFACT_DIRECTORIES = (
    "geometry",
    "score_fixtures",
    "design_pilots",
    "controller",
    "oracle",
    "plugin_baseline",
    "figures",
    "logs",
    "tests",
)
RESERVED_BUNDLE_PATHS = frozenset(
    {
        CHECKSUM_MANIFEST_NAME,
        EVIDENCE_ZIP_NAME,
        EVIDENCE_ZIP_SIDECAR_NAME,
    }
)
SOURCE_FREEZE_FORBIDDEN_PATHS = RESERVED_BUNDLE_PATHS | {
    "pre_pilot_source_freeze.json",
    "b2d2_design_freeze.json",
}
DEFAULT_SOURCE_DISCOVERY_SPEC = {
    "source_roots": ["b2d2", "tests"],
    "source_files": [
        "IMPLEMENTATION_PLAN.md",
        "SOURCE_BOUNDARY_PLAN.md",
        "run_b2d2.py",
        "structural_query_proofs.py",
    ],
}


class FinalizationError(RuntimeError):
    """Raised when an evidence freeze or bundle cannot be verified."""


def _fail(message: str) -> None:
    raise FinalizationError(message)


def _safe_relative(value: str, *, label: str = "path") -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        _fail(f"unsafe {label}: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value:
        _fail(f"non-canonical {label}: {value!r}")
    if any(part in {"", ".", ".."} or ":" in part for part in pure.parts):
        _fail(f"unsafe {label}: {value!r}")
    return value


def _path_under(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    relative = _safe_relative(relative)
    root_resolved = Path(root).resolve(strict=True)
    candidate = root_resolved.joinpath(*PurePosixPath(relative).parts)
    try:
        resolved = candidate.resolve(strict=must_exist)
    except FileNotFoundError as error:
        raise FinalizationError(f"missing path: {relative}") from error
    if resolved != root_resolved and root_resolved not in resolved.parents:
        _fail(f"path escapes root: {relative}")
    return candidate


def _regular_file(path: Path, *, label: str) -> Path:
    value = Path(path)
    if value.is_symlink() or not value.is_file():
        _fail(f"{label} is not a regular non-symlink file: {value}")
    return value


def _file_record(path: Path) -> dict[str, Any]:
    value = _regular_file(path, label="tracked file")
    return {"bytes": value.stat().st_size, "sha256": sha256_file(value)}


def discover_source_files(
    project_root: Path,
    *,
    source_roots: Sequence[str] = ("b2d2", "tests"),
    source_files: Sequence[str] = (
        "IMPLEMENTATION_PLAN.md",
        "SOURCE_BOUNDARY_PLAN.md",
        "run_b2d2.py",
        "structural_query_proofs.py",
    ),
) -> tuple[str, ...]:
    """Discover only declared B2-D2 source paths in canonical order."""

    root = Path(project_root)
    if not root.is_dir() or root.is_symlink():
        _fail(f"invalid project root: {root}")
    paths: set[str] = set()
    for relative_root in source_roots:
        relative_root = _safe_relative(relative_root, label="source root")
        directory = _path_under(root, relative_root)
        if directory.is_symlink() or not directory.is_dir():
            _fail(f"source root is not a real directory: {relative_root}")
        for path in directory.rglob("*"):
            if path.is_symlink():
                _fail(f"symlink in source tree: {path}")
            if path.is_dir():
                continue
            if not path.is_file():
                _fail(f"non-regular object in source tree: {path}")
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            paths.add(path.relative_to(root).as_posix())
    for relative in source_files:
        relative = _safe_relative(relative, label="source file")
        path = _path_under(root, relative)
        _regular_file(path, label="source file")
        paths.add(relative)
    return tuple(sorted(paths))


def _normalize_source_discovery_spec(
    source_discovery_spec: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Normalize the source boundary that an independent verifier must rescan."""

    if not isinstance(source_discovery_spec, Mapping):
        raise TypeError("source_discovery_spec must be a mapping")
    if set(source_discovery_spec) != {"source_roots", "source_files"}:
        _fail("source discovery spec must contain only source_roots/source_files")
    roots = [
        _safe_relative(str(value), label="source discovery root")
        for value in source_discovery_spec["source_roots"]
    ]
    files = [
        _safe_relative(str(value), label="source discovery file")
        for value in source_discovery_spec["source_files"]
    ]
    if len(roots) != len(set(roots)) or len(files) != len(set(files)):
        _fail("source discovery spec contains duplicate paths")
    if not roots and not files:
        _fail("source discovery spec may not be empty")
    return {"source_roots": sorted(roots), "source_files": sorted(files)}


def _independent_safe_relative(value: str) -> str:
    """Second, deliberately separate path validator for freeze verification."""

    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        _fail(f"independent verifier rejected path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value:
        _fail(f"independent verifier rejected non-canonical path: {value!r}")
    if any(part in {"", ".", ".."} or ":" in part for part in pure.parts):
        _fail(f"independent verifier rejected unsafe path: {value!r}")
    return value


def _independent_discover_source_files(
    project_root: Path,
    source_discovery_spec: Mapping[str, Any],
) -> tuple[str, ...]:
    """Rescan the declared source boundary without using discover_source_files."""

    root = Path(project_root)
    if root.is_symlink() or not root.is_dir():
        _fail(f"independent verifier rejected project root: {root}")
    root_resolved = root.resolve(strict=True)
    spec = _normalize_source_discovery_spec(source_discovery_spec)
    paths: set[str] = set()
    portable: set[str] = set()

    def add_path(path: Path) -> None:
        if path.is_symlink() or not path.is_file():
            _fail(f"independent verifier rejected source file: {path}")
        resolved = path.resolve(strict=True)
        if root_resolved not in resolved.parents:
            _fail(f"independent source path escapes project root: {path}")
        relative = _independent_safe_relative(path.relative_to(root).as_posix())
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            return
        folded = relative.casefold()
        if folded in portable and relative not in paths:
            _fail(f"independent source path collision: {relative}")
        paths.add(relative)
        portable.add(folded)

    for relative_root in spec["source_roots"]:
        directory = root.joinpath(*PurePosixPath(relative_root).parts)
        if directory.is_symlink() or not directory.is_dir():
            _fail(f"independent source root is invalid: {relative_root}")
        resolved = directory.resolve(strict=True)
        if resolved != root_resolved and root_resolved not in resolved.parents:
            _fail(f"independent source root escapes project: {relative_root}")
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                _fail(f"symlink in independently scanned source tree: {path}")
            if path.is_dir():
                continue
            add_path(path)
    for relative in spec["source_files"]:
        add_path(root.joinpath(*PurePosixPath(relative).parts))
    if not paths:
        _fail("independent source discovery found no files")
    return tuple(sorted(paths))


def _independent_canonical_bytes(value: Any) -> bytes:
    try:
        rendered = __import__("json").dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise FinalizationError("independent verifier found non-canonical JSON") from error
    return rendered.encode("utf-8")


def _independent_file_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def independently_verify_source_freeze(
    record: Mapping[str, Any],
    *,
    project_root: Path,
    frozen_payloads: Mapping[str, Any],
    digest_field: str = "b2d2_design_freeze_sha256",
    require_independent_flag: bool = True,
) -> dict[str, Any]:
    """Independently bind digest, exact source discovery, files, and payloads.

    This path intentionally does not call ``verify_source_freeze``,
    ``source_file_records``, ``_payload_records``, ``canonical_json``, or
    ``digest_json``.  It rescans the declared source roots so an added,
    untracked source file is fatal.
    """

    if digest_field not in record:
        _fail(f"independent verifier is missing digest field: {digest_field}")
    if record.get("verified") is not True:
        _fail("independent verifier requires the primary verified flag")
    if require_independent_flag and record.get("independent_verification") is not True:
        _fail("source freeze does not carry an independent-verification flag")
    spec = record.get("source_discovery")
    if not isinstance(spec, Mapping):
        _fail("source freeze lacks a source-discovery boundary")
    discovered = _independent_discover_source_files(project_root, spec)
    tracked = record.get("tracked_source_files")
    if not isinstance(tracked, Mapping) or tuple(sorted(tracked)) != discovered:
        _fail("independent exact source-set verification failed")
    independently_hashed = {
        relative: _independent_file_record(
            Path(project_root).joinpath(*PurePosixPath(relative).parts)
        )
        for relative in discovered
    }
    if independently_hashed != dict(tracked):
        _fail("independent source-file hash verification failed")

    payload_records: dict[str, dict[str, Any]] = {}
    for name in sorted(frozen_payloads):
        encoded = _independent_canonical_bytes(frozen_payloads[name])
        payload_records[str(name)] = {
            "canonical_bytes": len(encoded),
            "canonical_sha256": hashlib.sha256(encoded).hexdigest(),
        }
    if payload_records != record.get("frozen_payloads"):
        _fail("independent frozen-payload binding failed")

    core = {
        key: value
        for key, value in record.items()
        if key not in {digest_field, "verified", "independent_verification"}
    }
    recomputed = hashlib.sha256(_independent_canonical_bytes(core)).hexdigest()
    if recomputed != record.get(digest_field):
        _fail("independent canonical source-freeze digest mismatch")
    return {
        "recorded_sha256": record[digest_field],
        "recomputed_sha256": recomputed,
        "exact_discovered_source_count": len(discovered),
        "exact_source_set_verified": True,
        "source_files_verified": True,
        "frozen_payloads_verified": True,
        "verified": True,
    }


def source_file_records(
    project_root: Path,
    relative_paths: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """Hash an explicit source set, rejecting generated and locked paths."""

    root = Path(project_root)
    records: dict[str, dict[str, Any]] = {}
    portable_names: set[str] = set()
    for raw in relative_paths:
        relative = _safe_relative(str(raw), label="tracked source path")
        portable = relative.casefold()
        if relative in records or portable in portable_names:
            _fail(f"duplicate or case-colliding source path: {relative}")
        first = PurePosixPath(relative).parts[0]
        if first in {"locked_input", "artifacts", "tmp"}:
            _fail(f"forbidden source-freeze root: {relative}")
        if relative in SOURCE_FREEZE_FORBIDDEN_PATHS:
            _fail(f"cyclic/generated file cannot be source-frozen: {relative}")
        path = _path_under(root, relative)
        records[relative] = _file_record(path)
        portable_names.add(portable)
    if not records:
        _fail("source freeze must track at least one source file")
    return {relative: records[relative] for relative in sorted(records)}


def _payload_records(payloads: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in sorted(payloads):
        if not isinstance(name, str) or not name:
            _fail("frozen payload names must be non-empty strings")
        try:
            encoded = canonical_json(payloads[name]).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise FinalizationError(f"frozen payload is not strict JSON: {name}") from error
        result[name] = {
            "canonical_bytes": len(encoded),
            "canonical_sha256": hashlib.sha256(encoded).hexdigest(),
        }
    return result


def build_source_freeze(
    project_root: Path,
    tracked_sources: Iterable[str],
    *,
    frozen_payloads: Mapping[str, Any],
    source_discovery_spec: Mapping[str, Any],
    classification: str = "B2D2_VERIFIED_SOURCE_AND_DESIGN_FREEZE",
    digest_field: str = "b2d2_design_freeze_sha256",
    extra_core: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an acyclic canonical source/design freeze record."""

    if not digest_field or not isinstance(digest_field, str):
        raise TypeError("digest_field must be a non-empty string")
    core: dict[str, Any] = {
        "classification": str(classification),
        "canonicalization": "UTF8_SORTED_KEYS_COMPACT_JSON_NO_NAN",
        "tracked_source_files": source_file_records(project_root, tracked_sources),
        "frozen_payloads": _payload_records(frozen_payloads),
        "source_discovery": _normalize_source_discovery_spec(source_discovery_spec),
    }
    if extra_core is not None:
        collisions = set(core) & set(extra_core)
        forbidden = {digest_field, "verified", "independent_verification"}
        if collisions or forbidden & set(extra_core):
            _fail(
                "extra source-freeze fields collide with reserved fields: "
                f"{sorted(collisions | (forbidden & set(extra_core)))}"
            )
        core.update(dict(extra_core))
    record: dict[str, Any] = {
        **core,
        digest_field: digest_json(core),
        "verified": True,
        "independent_verification": False,
    }
    independently_verify_source_freeze(
        record,
        digest_field=digest_field,
        project_root=project_root,
        frozen_payloads=frozen_payloads,
        require_independent_flag=False,
    )
    record["independent_verification"] = True
    independently_verify_source_freeze(
        record,
        digest_field=digest_field,
        project_root=project_root,
        frozen_payloads=frozen_payloads,
    )
    return record


def build_design_freeze(
    project_root: Path,
    tracked_sources: Iterable[str],
    *,
    handoff_integrity: Any,
    selected_application_design: Any,
    geometry_manifest: Any,
    candidate_bank_manifest: Any,
    controller_contract: Any,
    gate_adjudication: Any,
    numerical_policy: Any,
    environment: Any,
    formal_b2_contract: Any,
    source_discovery_spec: Mapping[str, Any],
    classification: str = "B2D2_VERIFIED_SOURCE_AND_DESIGN_FREEZE",
    digest_field: str = "b2d2_design_freeze_sha256",
    extra_core: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the named B2-D2 design freeze from caller-supplied records."""

    payloads = {
        "handoff_integrity": handoff_integrity,
        "selected_application_design": selected_application_design,
        "geometry_manifest": geometry_manifest,
        "candidate_bank_manifest": candidate_bank_manifest,
        "controller_contract": controller_contract,
        "gate_adjudication": gate_adjudication,
        "numerical_policy": numerical_policy,
        "environment": environment,
        "formal_b2_contract": formal_b2_contract,
    }
    return build_source_freeze(
        project_root,
        tracked_sources,
        frozen_payloads=payloads,
        source_discovery_spec=source_discovery_spec,
        classification=classification,
        digest_field=digest_field,
        extra_core=extra_core,
    )


def verify_source_freeze(
    record: Mapping[str, Any],
    *,
    digest_field: str = "b2d2_design_freeze_sha256",
    project_root: Path | None = None,
    frozen_payloads: Mapping[str, Any] | None = None,
    require_independent: bool = True,
) -> dict[str, Any]:
    """Recompute a source-freeze digest and optionally all bound inputs."""

    if digest_field not in record:
        _fail(f"source freeze is missing {digest_field}")
    core = {
        key: value
        for key, value in record.items()
        if key not in {digest_field, "verified", "independent_verification"}
    }
    recomputed = digest_json(core)
    recorded = record.get(digest_field)
    if recorded != recomputed or record.get("verified") is not True:
        _fail("source-freeze canonical digest mismatch")
    if require_independent and record.get("independent_verification") is not True:
        _fail("source freeze lacks independent verification")
    source_match: bool | None = None
    if project_root is not None:
        observed_sources = source_file_records(
            project_root, record.get("tracked_source_files", {}).keys()
        )
        source_match = observed_sources == record.get("tracked_source_files")
        if not source_match:
            _fail("source files changed after freeze")
    payload_match: bool | None = None
    if frozen_payloads is not None:
        payload_match = _payload_records(frozen_payloads) == record.get(
            "frozen_payloads"
        )
        if not payload_match:
            _fail("frozen payload binding mismatch")
    return {
        "recorded_sha256": recorded,
        "recomputed_sha256": recomputed,
        "source_files_verified": source_match,
        "frozen_payloads_verified": payload_match,
        "verified": True,
    }


def write_source_freeze(
    path: Path,
    record: Mapping[str, Any],
    *,
    digest_field: str = "b2d2_design_freeze_sha256",
) -> Path:
    verify_source_freeze(record, digest_field=digest_field)
    try:
        return write_json(path, dict(record), overwrite=False)
    except ReportingError as error:
        raise FinalizationError(str(error)) from error


def _artifact_files(root: Path) -> dict[str, Path]:
    value = Path(root)
    if not value.is_dir() or value.is_symlink():
        _fail(f"artifact root is not a real directory: {value}")
    result: dict[str, Path] = {}
    portable_names: set[str] = set()
    for path in sorted(value.rglob("*")):
        if path.is_symlink():
            _fail(f"symlink is forbidden in artifact tree: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            _fail(f"non-regular object in artifact tree: {path}")
        relative = _safe_relative(path.relative_to(value).as_posix(), label="artifact path")
        portable = relative.casefold()
        if portable in portable_names:
            _fail(f"portable path collision in artifact tree: {relative}")
        result[relative] = path
        portable_names.add(portable)
    return result


def artifact_checksum_records(root: Path) -> dict[str, str]:
    """Hash every payload file while excluding the three acyclic reserves."""

    files = _artifact_files(root)
    return {
        relative: sha256_file(files[relative])
        for relative in sorted(files)
        if relative not in RESERVED_BUNDLE_PATHS
    }


def write_checksum_tree(
    artifact_root: Path,
    *,
    manifest_name: str = CHECKSUM_MANIFEST_NAME,
) -> dict[str, Any]:
    """Write the deterministic artifact checksum tree exactly once."""

    root = Path(artifact_root)
    manifest_name = _safe_relative(manifest_name, label="manifest name")
    if manifest_name != CHECKSUM_MANIFEST_NAME:
        _fail("evidence checksum manifest must be checksums.sha256")
    files = _artifact_files(root)
    present_reserves = sorted(RESERVED_BUNDLE_PATHS & set(files))
    if present_reserves:
        _fail(f"bundle reserve already exists: {present_reserves}")
    records = artifact_checksum_records(root)
    payload = render_sha256_manifest(records)
    try:
        write_text(root / manifest_name, payload.decode("utf-8"), overwrite=False)
    except (ReportingError, IntegrityError) as error:
        raise FinalizationError(str(error)) from error
    verified = verify_checksum_tree(root)
    if verified["records"] != records:
        _fail("artifact tree changed while checksum manifest was written")
    return verified


def verify_checksum_tree(
    artifact_root: Path,
    *,
    manifest_name: str = CHECKSUM_MANIFEST_NAME,
) -> dict[str, Any]:
    root = Path(artifact_root)
    manifest_name = _safe_relative(manifest_name, label="manifest name")
    files = _artifact_files(root)
    if manifest_name not in files:
        _fail(f"missing artifact checksum manifest: {manifest_name}")
    try:
        records = parse_sha256_manifest(files[manifest_name].read_bytes())
    except IntegrityError as error:
        raise FinalizationError(str(error)) from error
    if set(records) & RESERVED_BUNDLE_PATHS:
        _fail("checksum tree contains a cyclic reserved path")
    payload_paths = set(files) - RESERVED_BUNDLE_PATHS
    payload_paths.discard(manifest_name)
    if payload_paths != set(records):
        _fail(
            "artifact checksum path mismatch; "
            f"missing={sorted(set(records) - payload_paths)}, "
            f"unexpected={sorted(payload_paths - set(records))}"
        )
    mismatches = [
        relative
        for relative, expected in records.items()
        if sha256_file(files[relative]) != expected
    ]
    if mismatches:
        _fail(f"artifact checksum mismatches: {mismatches}")
    return {
        "manifest_sha256": sha256_file(files[manifest_name]),
        "entry_count": len(records),
        "hash_tree_sha256": digest_json(records),
        "records": records,
        "verified": True,
    }


def assert_output_contract(
    artifact_root: Path,
    *,
    required_files: Sequence[str] = REQUIRED_ARTIFACT_FILES,
    required_directories: Sequence[str] = REQUIRED_ARTIFACT_DIRECTORIES,
    minimum_figure_count: int = 8,
    exact_top_level: bool = True,
) -> dict[str, Any]:
    """Validate the declared artifact names without deriving any results."""

    root = Path(artifact_root)
    if not root.is_dir() or root.is_symlink():
        _fail(f"invalid artifact root: {root}")
    normalized_files = tuple(_safe_relative(x, label="required file") for x in required_files)
    normalized_dirs = tuple(
        _safe_relative(x, label="required directory") for x in required_directories
    )
    for relative in normalized_files:
        _regular_file(_path_under(root, relative), label="required artifact")
    for relative in normalized_dirs:
        path = _path_under(root, relative)
        if path.is_symlink() or not path.is_dir():
            _fail(f"required artifact directory is invalid: {relative}")
    figures = root / "figures"
    observed_figures = (
        [path for path in figures.rglob("*.png") if path.is_file() and not path.is_symlink()]
        if figures.is_dir() and not figures.is_symlink()
        else []
    )
    if len(observed_figures) < int(minimum_figure_count):
        _fail(
            f"required figure count mismatch: expected at least "
            f"{int(minimum_figure_count)}, observed {len(observed_figures)}"
        )
    if exact_top_level:
        expected = {PurePosixPath(x).parts[0] for x in normalized_files} | {
            PurePosixPath(x).parts[0] for x in normalized_dirs
        }
        observed = {path.name for path in root.iterdir()}
        if observed != expected:
            _fail(
                "artifact top-level contract mismatch; "
                f"missing={sorted(expected - observed)}, "
                f"unexpected={sorted(observed - expected)}"
            )
    return {
        "required_file_count": len(normalized_files),
        "required_directory_count": len(normalized_dirs),
        "figure_count": len(observed_figures),
        "verified": True,
    }


def create_deterministic_zip(
    artifact_root: Path,
    *,
    zip_name: str = EVIDENCE_ZIP_NAME,
    compression: int = ZIP_DEFLATED,
    compresslevel: int = 9,
) -> dict[str, Any]:
    """Create a normalized ZIP from the verified checksum-covered tree."""

    root = Path(artifact_root)
    zip_name = _safe_relative(zip_name, label="ZIP name")
    if zip_name != EVIDENCE_ZIP_NAME:
        _fail("evidence ZIP must be evidence_bundle.zip")
    zip_path = root / zip_name
    if zip_path.exists() or zip_path.is_symlink():
        _fail(f"refusing to overwrite evidence ZIP: {zip_path}")
    if (root / EVIDENCE_ZIP_SIDECAR_NAME).exists():
        _fail("ZIP sidecar must not exist before ZIP creation")
    tree = verify_checksum_tree(root)
    member_names = sorted(tree["records"]) + [CHECKSUM_MANIFEST_NAME]
    # The manifest sorts before some payloads; sort the complete member set.
    member_names = sorted(member_names)
    created = False
    try:
        with ZipFile(
            zip_path,
            mode="x",
            compression=compression,
            compresslevel=int(compresslevel),
            strict_timestamps=True,
        ) as archive:
            created = True
            archive.comment = b""
            for relative in member_names:
                path = _regular_file(root / relative, label="ZIP source")
                if relative in tree["records"]:
                    observed = sha256_file(path)
                    if observed != tree["records"][relative]:
                        _fail(f"artifact changed before ZIP creation: {relative}")
                info = ZipInfo(relative, date_time=FIXED_ZIP_TIMESTAMP)
                info.create_system = 3
                info.external_attr = ZIP_FILE_MODE << 16
                info.compress_type = compression
                info.extra = b""
                info.comment = b""
                archive.writestr(
                    info,
                    path.read_bytes(),
                    compress_type=compression,
                    compresslevel=int(compresslevel),
                )
    except Exception:
        if created and zip_path.exists():
            zip_path.unlink()
        raise
    verification = verify_evidence_bundle(root, zip_name=zip_name)
    return verification


def _hash_zip_member(archive: ZipFile, info: ZipInfo) -> str:
    digest = hashlib.sha256()
    try:
        with archive.open(info, "r") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except (BadZipFile, RuntimeError, OSError) as error:
        raise FinalizationError(f"ZIP CRC/read failure: {info.filename}") from error
    return digest.hexdigest()


def verify_evidence_bundle(
    artifact_root: Path,
    *,
    zip_name: str = EVIDENCE_ZIP_NAME,
    expected_zip_sha256: str | None = None,
) -> dict[str, Any]:
    """Reopen and independently verify every deterministic ZIP member."""

    root = Path(artifact_root)
    tree = verify_checksum_tree(root)
    zip_path = _regular_file(root / zip_name, label="evidence ZIP")
    observed_zip_sha256 = sha256_file(zip_path)
    if expected_zip_sha256 is not None and observed_zip_sha256 != expected_zip_sha256:
        _fail("evidence ZIP SHA-256 mismatch")
    expected_members = set(tree["records"]) | {CHECKSUM_MANIFEST_NAME}
    try:
        with ZipFile(zip_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != expected_members:
                _fail("evidence ZIP member paths do not match checksum tree")
            if names != sorted(names):
                _fail("evidence ZIP members are not in deterministic order")
            by_name: dict[str, ZipInfo] = {}
            portable_names: set[str] = set()
            for info in infos:
                name = _safe_relative(info.filename, label="ZIP member")
                portable = name.casefold()
                if portable in portable_names:
                    _fail(f"case-colliding ZIP member: {name}")
                if info.is_dir() or info.flag_bits & 0x1:
                    _fail(f"invalid ZIP member type: {name}")
                mode = (info.external_attr >> 16) & 0xFFFF
                if (
                    info.date_time != FIXED_ZIP_TIMESTAMP
                    or info.create_system != 3
                    or mode != ZIP_FILE_MODE
                    or info.compress_type != ZIP_DEFLATED
                    or info.extra
                    or info.comment
                ):
                    _fail(f"non-deterministic ZIP metadata: {name}")
                by_name[name] = info
                portable_names.add(portable)
            if archive.comment:
                _fail("evidence ZIP comment must be empty")
            embedded_manifest = archive.read(by_name[CHECKSUM_MANIFEST_NAME])
            disk_manifest = (root / CHECKSUM_MANIFEST_NAME).read_bytes()
            if embedded_manifest != disk_manifest:
                _fail("embedded and external checksum manifests differ")
            try:
                embedded_records = parse_sha256_manifest(embedded_manifest)
            except IntegrityError as error:
                raise FinalizationError(str(error)) from error
            if embedded_records != tree["records"]:
                _fail("embedded checksum records differ from disk verification")
            for relative, expected in embedded_records.items():
                if _hash_zip_member(archive, by_name[relative]) != expected:
                    _fail(f"evidence ZIP member checksum mismatch: {relative}")
            # Reading the manifest above also makes zipfile validate its CRC.
    except (BadZipFile, KeyError, OSError) as error:
        raise FinalizationError(f"cannot reopen evidence ZIP: {zip_path}") from error
    return {
        "zip_sha256": observed_zip_sha256,
        "member_count": len(expected_members),
        "checksum_count": len(tree["records"]),
        "crc_verified_member_count": len(expected_members),
        "member_set_sha256": digest_json(sorted(expected_members)),
        "member_hash_tree_sha256": tree["hash_tree_sha256"],
        "deterministic_metadata_verified": True,
        "verified": True,
    }


def _ensure_zip_hash_external_only(artifact_root: Path, zip_sha256: str) -> None:
    needle = zip_sha256.encode("ascii")
    for relative, path in _artifact_files(artifact_root).items():
        if relative in {EVIDENCE_ZIP_NAME, EVIDENCE_ZIP_SIDECAR_NAME}:
            continue
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                if needle in chunk:
                    _fail(f"ZIP SHA-256 appears inside bundled artifact: {relative}")


def write_zip_sidecar(
    artifact_root: Path,
    zip_sha256: str,
) -> dict[str, Any]:
    root = Path(artifact_root)
    if len(zip_sha256) != 64 or any(c not in "0123456789abcdef" for c in zip_sha256):
        _fail("invalid evidence ZIP SHA-256")
    zip_path = _regular_file(root / EVIDENCE_ZIP_NAME, label="evidence ZIP")
    if sha256_file(zip_path) != zip_sha256:
        _fail("sidecar digest does not match evidence ZIP")
    _ensure_zip_hash_external_only(root, zip_sha256)
    sidecar_path = root / EVIDENCE_ZIP_SIDECAR_NAME
    text = f"{zip_sha256}  {EVIDENCE_ZIP_NAME}\n"
    try:
        write_text(sidecar_path, text, overwrite=False)
    except ReportingError as error:
        raise FinalizationError(str(error)) from error
    return verify_zip_sidecar(root)


def verify_zip_sidecar(artifact_root: Path) -> dict[str, Any]:
    root = Path(artifact_root)
    zip_path = _regular_file(root / EVIDENCE_ZIP_NAME, label="evidence ZIP")
    sidecar = _regular_file(
        root / EVIDENCE_ZIP_SIDECAR_NAME, label="evidence ZIP sidecar"
    )
    digest = sha256_file(zip_path)
    expected = f"{digest}  {EVIDENCE_ZIP_NAME}\n".encode("ascii")
    if sidecar.read_bytes() != expected:
        _fail("external evidence ZIP sidecar is not exact")
    _ensure_zip_hash_external_only(root, digest)
    return {
        "zip_sha256": digest,
        "sidecar": EVIDENCE_ZIP_SIDECAR_NAME,
        "external_only": True,
        "verified": True,
    }


def finalize_evidence_bundle(
    artifact_root: Path,
    *,
    required_files: Sequence[str] | None = None,
    required_directories: Sequence[str] | None = None,
    minimum_figure_count: int = 8,
    exact_top_level: bool = True,
) -> dict[str, Any]:
    """Validate, checksum, ZIP, reopen, and sidecar a fresh artifact tree."""

    payload_files = (
        REQUIRED_PREBUNDLE_FILES if required_files is None else tuple(required_files)
    )
    directories = (
        REQUIRED_ARTIFACT_DIRECTORIES
        if required_directories is None
        else tuple(required_directories)
    )
    pre_contract = assert_output_contract(
        artifact_root,
        required_files=payload_files,
        required_directories=directories,
        minimum_figure_count=minimum_figure_count,
        exact_top_level=exact_top_level,
    )
    checksums = write_checksum_tree(artifact_root)
    bundle = create_deterministic_zip(artifact_root)
    reopened = verify_evidence_bundle(
        artifact_root, expected_zip_sha256=bundle["zip_sha256"]
    )
    sidecar = write_zip_sidecar(artifact_root, bundle["zip_sha256"])
    final_contract = assert_output_contract(
        artifact_root,
        required_files=tuple(payload_files)
        + (
            CHECKSUM_MANIFEST_NAME,
            EVIDENCE_ZIP_NAME,
            EVIDENCE_ZIP_SIDECAR_NAME,
        ),
        required_directories=directories,
        minimum_figure_count=minimum_figure_count,
        exact_top_level=exact_top_level,
    )
    return {
        "prebundle_contract": pre_contract,
        "checksum_tree": checksums,
        "bundle": bundle,
        "reopened_verification": reopened,
        "external_sidecar": sidecar,
        "final_contract": final_contract,
        "verified": True,
    }


__all__ = [
    "CHECKSUM_MANIFEST_NAME",
    "DEFAULT_SOURCE_DISCOVERY_SPEC",
    "EVIDENCE_ZIP_NAME",
    "EVIDENCE_ZIP_SIDECAR_NAME",
    "FIXED_ZIP_TIMESTAMP",
    "FinalizationError",
    "REQUIRED_ARTIFACT_DIRECTORIES",
    "REQUIRED_ARTIFACT_FILES",
    "REQUIRED_PREBUNDLE_FILES",
    "artifact_checksum_records",
    "assert_output_contract",
    "build_design_freeze",
    "build_source_freeze",
    "create_deterministic_zip",
    "discover_source_files",
    "finalize_evidence_bundle",
    "independently_verify_source_freeze",
    "source_file_records",
    "verify_checksum_tree",
    "verify_evidence_bundle",
    "verify_source_freeze",
    "verify_zip_sidecar",
    "write_checksum_tree",
    "write_source_freeze",
    "write_zip_sidecar",
]
