"""Read-only integrity verification helpers for the B2-D2 lifecycle.

This module deliberately has no dependency on predecessor source code.  It
verifies the locked handoff and the embedded B1.1 evidence archive in place;
archives are never extracted and locked inputs are never opened for writing.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any
from zipfile import BadZipFile, ZipFile, ZipInfo

from .util import canonical_json, digest_json, sha256_file


EXPECTED_HANDOFF_ZIP_SHA256 = (
    "5b3c8472ae318da4fd3c55109f257161b2ebf4d8f9b371f729a8ded4aa6aba23"
)
EXPECTED_HANDOFF_CHECKSUM_COUNT = 37
EXPECTED_PREDECESSOR_ZIP_SHA256 = (
    "2095d8c17081cc9e574f5e052b2a1100864eff499610c45ef2c999905bf67c83"
)
EXPECTED_PREDECESSOR_MEMBER_COUNT = 3636
EXPECTED_PREDECESSOR_CHECKSUM_COUNT = 3635
EXPECTED_B1_FREEZE_SHA256 = (
    "a263cc2fe0a97a448b66722608494ed88908994088c219bceccfa79bd1e6390f"
)
EXPECTED_B11_FREEZE_SHA256 = (
    "742bf3baba3126cafbe30ae2b8ce05d5b71be57a9b75d174c338fbee04b705ee"
)
EXPECTED_B11_TERMINAL_STATUS = (
    "PASS_ARA_B11_ORACLE_AUDIT_COMPLETED_AND_B1_VALIDATED"
)
EXPECTED_D0_2_ZIP_SHA256 = (
    "d6488b58885366b034ce10027fb934ef44cb0ff919c7317c3c0d200a54c9cd10"
)
EXPECTED_D0_2_MEMBER_COUNT = 276
EXPECTED_D0_2_CHECKSUM_COUNT = 275
EXPECTED_D0_2_TERMINAL_STATUS = "HOLD_ARA_B2D02_APPLICATION_DESIGN_NOT_FOUND"

HANDOFF_MANIFEST_NAME = "HANDOFF_CHECKSUMS.sha256"
PREDECESSOR_ARCHIVE_RELATIVE_PATH = (
    "reference/B11_VALIDATED_GLOBAL_CONTROLLER_EVIDENCE.zip"
)
D0_2_ARCHIVE_RELATIVE_PATH = "reference/B2D02_NONPASS_EVIDENCE_BUNDLE.zip"
PREDECESSOR_MANIFEST_NAME = "checksums.sha256"
B1_FREEZE_MEMBER = "read_only_b1/code_freeze.json"
B11_FREEZE_MEMBER = "b11_code_freeze.json"
B11_TERMINAL_MEMBER = "terminal_status.json"
B11_READJUDICATION_MEMBER = "b1_readjudication.json"

_MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  (.+)")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class IntegrityError(RuntimeError):
    """Raised when a locked input or evidence invariant does not hold."""


def _fail(message: str) -> None:
    raise IntegrityError(message)


def _require_sha256(value: str, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail(f"{label} must be a lowercase hexadecimal SHA-256 digest")
    return value


def _validated_relative_path(value: str, *, label: str = "path") -> str:
    """Return a canonical, traversal-free POSIX relative path."""

    if not isinstance(value, str) or not value:
        _fail(f"{label} is empty")
    if "\\" in value or "\x00" in value or value.startswith("/"):
        _fail(f"unsafe {label}: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value:
        _fail(f"non-canonical {label}: {value!r}")
    if any(part in {"", ".", ".."} for part in pure.parts):
        _fail(f"unsafe {label}: {value!r}")
    # Colons permit drive-qualified or alternate-data-stream paths on Windows.
    if any(":" in part for part in pure.parts):
        _fail(f"unsafe {label}: {value!r}")
    return value


def parse_sha256_manifest(
    payload: bytes | str,
    *,
    expected_count: int | None = None,
    require_sorted: bool = True,
) -> dict[str, str]:
    """Parse the strict ``<digest><two spaces><POSIX path>`` format.

    Duplicate paths, portable case collisions, traversal paths, non-lowercase
    digests, blank lines, and non-canonical ordering are rejected.
    """

    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise IntegrityError("checksum manifest is not UTF-8") from error
    elif isinstance(payload, str):
        text = payload
    else:
        raise TypeError("manifest payload must be bytes or str")
    if "\x00" in text:
        _fail("checksum manifest contains NUL")
    lines = text.splitlines()
    if not lines or any(not line for line in lines):
        _fail("checksum manifest must contain only non-empty lines")

    result: dict[str, str] = {}
    portable_names: set[str] = set()
    ordered_paths: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        match = _MANIFEST_LINE.fullmatch(line)
        if match is None:
            _fail(f"invalid checksum manifest line {line_number}")
        digest, relative = match.groups()
        _require_sha256(digest, label=f"manifest line {line_number} digest")
        relative = _validated_relative_path(
            relative, label=f"manifest line {line_number} path"
        )
        portable = relative.casefold()
        if relative in result or portable in portable_names:
            _fail(f"duplicate or case-colliding manifest path: {relative}")
        result[relative] = digest
        portable_names.add(portable)
        ordered_paths.append(relative)

    if require_sorted and ordered_paths != sorted(ordered_paths):
        _fail("checksum manifest paths are not in canonical order")
    if expected_count is not None and len(result) != int(expected_count):
        _fail(
            "checksum manifest entry count mismatch: "
            f"expected {int(expected_count)}, observed {len(result)}"
        )
    return result


def render_sha256_manifest(records: Mapping[str, str]) -> bytes:
    """Render a canonical checksum tree without adding a self-entry."""

    normalized: dict[str, str] = {}
    portable_names: set[str] = set()
    for relative, digest in records.items():
        path = _validated_relative_path(str(relative))
        portable = path.casefold()
        if path in normalized or portable in portable_names:
            _fail(f"duplicate or case-colliding manifest path: {path}")
        normalized[path] = _require_sha256(str(digest), label=path)
        portable_names.add(portable)
    return (
        "".join(
            f"{normalized[path]}  {path}\n" for path in sorted(normalized)
        ).encode("utf-8")
    )


def _tree_files(root: Path) -> dict[str, Path]:
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        _fail(f"not a real directory: {root}")
    files: dict[str, Path] = {}
    portable_names: set[str] = set()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            _fail(f"symlink is forbidden in locked tree: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            _fail(f"non-regular object in locked tree: {path}")
        relative = _validated_relative_path(
            path.relative_to(root).as_posix(), label="tree path"
        )
        portable = relative.casefold()
        if portable in portable_names:
            _fail(f"portable path collision in locked tree: {relative}")
        files[relative] = path
        portable_names.add(portable)
    return files


def _file_is_read_only(path: Path) -> bool:
    return (path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)) == 0


def verify_directory_checksum_tree(
    root: Path,
    *,
    manifest_name: str = HANDOFF_MANIFEST_NAME,
    expected_count: int | None = None,
    require_read_only: bool = False,
) -> dict[str, Any]:
    """Verify a directory checksum tree, including exact path coverage."""

    root = Path(root)
    manifest_name = _validated_relative_path(manifest_name, label="manifest name")
    files = _tree_files(root)
    if manifest_name not in files:
        _fail(f"missing checksum manifest: {manifest_name}")
    records = parse_sha256_manifest(
        files[manifest_name].read_bytes(), expected_count=expected_count
    )
    if manifest_name in records:
        _fail("checksum manifest may not contain itself")
    expected_paths = set(records) | {manifest_name}
    observed_paths = set(files)
    if observed_paths != expected_paths:
        missing = sorted(expected_paths - observed_paths)
        unexpected = sorted(observed_paths - expected_paths)
        _fail(
            f"checksum tree path mismatch; missing={missing}, "
            f"unexpected={unexpected}"
        )

    failures: list[str] = []
    for relative, expected in records.items():
        observed = sha256_file(files[relative])
        if observed != expected:
            failures.append(relative)
    if failures:
        _fail(f"checksum mismatches: {failures}")
    writable = sorted(
        relative for relative, path in files.items() if not _file_is_read_only(path)
    )
    if require_read_only and writable:
        _fail(f"locked input contains writable files: {writable}")
    return {
        "manifest": manifest_name,
        "manifest_sha256": sha256_file(files[manifest_name]),
        "verified_file_count": len(records),
        "tree_file_count": len(files),
        "writable_files": writable,
        "hash_tree_sha256": digest_json(records),
        "verified": True,
    }


def _zip_mode(info: ZipInfo) -> int:
    return (info.external_attr >> 16) & 0xFFFF


def _validate_zip_infos(
    infos: list[ZipInfo],
    *,
    expected_member_count: int | None,
    require_read_only: bool,
) -> dict[str, ZipInfo]:
    if expected_member_count is not None and len(infos) != int(expected_member_count):
        _fail(
            "ZIP member count mismatch: "
            f"expected {int(expected_member_count)}, observed {len(infos)}"
        )
    by_name: dict[str, ZipInfo] = {}
    portable_names: set[str] = set()
    writable: list[str] = []
    for info in infos:
        name = _validated_relative_path(info.filename, label="ZIP member path")
        portable = name.casefold()
        if name in by_name or portable in portable_names:
            _fail(f"duplicate or case-colliding ZIP member: {name}")
        if info.is_dir() or name.endswith("/"):
            _fail(f"directory ZIP members are forbidden: {name}")
        if info.flag_bits & 0x1:
            _fail(f"encrypted ZIP member is forbidden: {name}")
        mode = _zip_mode(info)
        file_type = stat.S_IFMT(mode)
        if file_type == stat.S_IFLNK:
            _fail(f"symlink ZIP member is forbidden: {name}")
        if file_type not in {0, stat.S_IFREG}:
            _fail(f"non-regular ZIP member is forbidden: {name}")
        if mode and mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            writable.append(name)
        by_name[name] = info
        portable_names.add(portable)
    if require_read_only and writable:
        _fail(f"ZIP contains writable members: {writable}")
    return by_name


def _hash_zip_member(archive: ZipFile, info: ZipInfo) -> str:
    digest = hashlib.sha256()
    try:
        with archive.open(info, "r") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except (BadZipFile, RuntimeError, OSError) as error:
        raise IntegrityError(f"failed ZIP CRC/read verification: {info.filename}") from error
    return digest.hexdigest()


def _strict_json(payload: bytes, *, label: str) -> dict[str, Any]:
    def object_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"duplicate JSON key in {label}: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        _fail(f"non-finite JSON constant in {label}: {value}")

    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=object_hook,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntegrityError(f"invalid JSON in {label}") from error
    if not isinstance(value, dict):
        _fail(f"{label} must contain a JSON object")
    return value


def verify_handoff_bundle(
    handoff_root: Path,
    handoff_zip: Path,
    *,
    expected_zip_sha256: str = EXPECTED_HANDOFF_ZIP_SHA256,
    expected_manifest_count: int = EXPECTED_HANDOFF_CHECKSUM_COUNT,
    expected_archive_member_count: int | None = None,
    manifest_name: str = HANDOFF_MANIFEST_NAME,
    require_read_only: bool = True,
) -> dict[str, Any]:
    """Verify the extracted handoff and its exact outer ZIP, read-only."""

    root = Path(handoff_root)
    archive_path = Path(handoff_zip)
    _require_sha256(expected_zip_sha256, label="expected handoff ZIP SHA-256")
    if not archive_path.is_file() or archive_path.is_symlink():
        _fail(f"handoff ZIP is not a regular file: {archive_path}")
    observed_zip_sha256 = sha256_file(archive_path)
    if observed_zip_sha256 != expected_zip_sha256:
        _fail("outer handoff ZIP SHA-256 mismatch")

    directory = verify_directory_checksum_tree(
        root,
        manifest_name=manifest_name,
        expected_count=expected_manifest_count,
        require_read_only=require_read_only,
    )
    disk_files = _tree_files(root)
    expected_archive_member_count = (
        len(disk_files)
        if expected_archive_member_count is None
        else int(expected_archive_member_count)
    )
    prefix = _validated_relative_path(root.name, label="handoff ZIP prefix")
    try:
        with ZipFile(archive_path, "r") as archive:
            infos = _validate_zip_infos(
                archive.infolist(),
                expected_member_count=expected_archive_member_count,
                # The extracted handoff is locked read-only.  The supplied
                # transport ZIP canonically records 0644 regular files, so
                # writability metadata is not a lock assertion for this
                # outer transport layer.
                require_read_only=False,
            )
            inner_infos: dict[str, ZipInfo] = {}
            for name, info in infos.items():
                expected_prefix = f"{prefix}/"
                if not name.startswith(expected_prefix):
                    _fail(f"ZIP member is outside exact handoff prefix: {name}")
                relative = _validated_relative_path(
                    name[len(expected_prefix) :], label="handoff member path"
                )
                if relative in inner_infos:
                    _fail(f"duplicate handoff member path: {relative}")
                inner_infos[relative] = info
            if set(inner_infos) != set(disk_files):
                _fail("outer ZIP paths do not exactly match extracted handoff")
            for relative in sorted(inner_infos):
                archived = _hash_zip_member(archive, inner_infos[relative])
                observed = sha256_file(disk_files[relative])
                if archived != observed:
                    _fail(f"outer ZIP/extracted content mismatch: {relative}")
    except (BadZipFile, OSError) as error:
        raise IntegrityError(f"cannot verify handoff ZIP: {archive_path}") from error

    return {
        "outer_zip_sha256": observed_zip_sha256,
        "outer_zip_member_count": expected_archive_member_count,
        "outer_zip_crc_verified": True,
        "extracted_tree": directory,
        "archive_matches_extracted_tree": True,
        "verified": True,
    }


def recompute_freeze_sha256(
    record: Mapping[str, Any],
    *,
    digest_field: str,
    excluded_fields: tuple[str, ...] = ("verified", "independent_verification"),
) -> str:
    """Recompute the inherited canonical freeze digest without self-fields."""

    if digest_field not in record:
        _fail(f"freeze record is missing {digest_field}")
    excluded = {digest_field, *excluded_fields}
    core = {key: value for key, value in record.items() if key not in excluded}
    return digest_json(core)


def verify_freeze_record(
    record: Mapping[str, Any],
    *,
    digest_field: str,
    expected_sha256: str,
    require_independent: bool = True,
) -> dict[str, Any]:
    expected_sha256 = _require_sha256(expected_sha256, label=digest_field)
    recorded = record.get(digest_field)
    recomputed = recompute_freeze_sha256(record, digest_field=digest_field)
    flags_valid = record.get("verified") is True and (
        record.get("independent_verification") is True or not require_independent
    )
    if recorded != expected_sha256 or recomputed != expected_sha256 or not flags_valid:
        _fail(f"canonical freeze verification failed for {digest_field}")
    return {
        "digest_field": digest_field,
        "recorded_sha256": recorded,
        "recomputed_sha256": recomputed,
        "independent_verification": record.get("independent_verification") is True,
        "verified": True,
    }


def verify_predecessor_evidence(
    evidence_zip: Path,
    *,
    expected_zip_sha256: str = EXPECTED_PREDECESSOR_ZIP_SHA256,
    expected_member_count: int = EXPECTED_PREDECESSOR_MEMBER_COUNT,
    expected_checksum_count: int = EXPECTED_PREDECESSOR_CHECKSUM_COUNT,
    expected_b1_freeze_sha256: str = EXPECTED_B1_FREEZE_SHA256,
    expected_b11_freeze_sha256: str = EXPECTED_B11_FREEZE_SHA256,
    expected_terminal_status: str = EXPECTED_B11_TERMINAL_STATUS,
    manifest_name: str = PREDECESSOR_MANIFEST_NAME,
    require_read_only: bool = True,
) -> dict[str, Any]:
    """Reopen and fully verify the immutable B1.1 evidence archive.

    Every member is streamed to EOF, which makes ``zipfile`` validate its CRC,
    and every non-manifest member is checked against the embedded checksum
    tree.  No archive member is extracted or executed.
    """

    path = Path(evidence_zip)
    for digest, label in (
        (expected_zip_sha256, "expected predecessor ZIP SHA-256"),
        (expected_b1_freeze_sha256, "expected B1 freeze SHA-256"),
        (expected_b11_freeze_sha256, "expected B1.1 freeze SHA-256"),
    ):
        _require_sha256(digest, label=label)
    if not path.is_file() or path.is_symlink():
        _fail(f"predecessor evidence ZIP is not a regular file: {path}")
    observed_zip_sha256 = sha256_file(path)
    if observed_zip_sha256 != expected_zip_sha256:
        _fail("predecessor evidence ZIP SHA-256 mismatch")

    manifest_name = _validated_relative_path(manifest_name, label="manifest name")
    required_records = {
        B1_FREEZE_MEMBER,
        B11_FREEZE_MEMBER,
        B11_TERMINAL_MEMBER,
        B11_READJUDICATION_MEMBER,
    }
    try:
        with ZipFile(path, "r") as archive:
            infos = _validate_zip_infos(
                archive.infolist(),
                expected_member_count=expected_member_count,
                require_read_only=require_read_only,
            )
            if manifest_name not in infos:
                _fail(f"predecessor archive is missing {manifest_name}")
            manifest_payload = archive.read(infos[manifest_name])
            records = parse_sha256_manifest(
                manifest_payload, expected_count=expected_checksum_count
            )
            if manifest_name in records:
                _fail("predecessor checksum manifest may not contain itself")
            if set(infos) != set(records) | {manifest_name}:
                _fail("predecessor ZIP and checksum tree paths differ")
            if not required_records.issubset(records):
                _fail("predecessor archive is missing a required adjudication record")

            for relative in sorted(records):
                observed = _hash_zip_member(archive, infos[relative])
                if observed != records[relative]:
                    _fail(f"predecessor member checksum mismatch: {relative}")

            b1_record = _strict_json(
                archive.read(infos[B1_FREEZE_MEMBER]), label=B1_FREEZE_MEMBER
            )
            b11_record = _strict_json(
                archive.read(infos[B11_FREEZE_MEMBER]), label=B11_FREEZE_MEMBER
            )
            terminal = _strict_json(
                archive.read(infos[B11_TERMINAL_MEMBER]),
                label=B11_TERMINAL_MEMBER,
            )
            readjudication = _strict_json(
                archive.read(infos[B11_READJUDICATION_MEMBER]),
                label=B11_READJUDICATION_MEMBER,
            )
    except (BadZipFile, KeyError, OSError, RuntimeError) as error:
        if isinstance(error, IntegrityError):
            raise
        raise IntegrityError(f"cannot verify predecessor evidence ZIP: {path}") from error

    b1_freeze = verify_freeze_record(
        b1_record,
        digest_field="code_freeze_sha256",
        expected_sha256=expected_b1_freeze_sha256,
    )
    b11_freeze = verify_freeze_record(
        b11_record,
        digest_field="b11_code_freeze_sha256",
        expected_sha256=expected_b11_freeze_sha256,
    )
    terminal_checks = (
        terminal.get("terminal_status") == expected_terminal_status,
        terminal.get("b1_code_freeze_sha256") == expected_b1_freeze_sha256,
        terminal.get("b11_code_freeze_sha256") == expected_b11_freeze_sha256,
        terminal.get("original_b1_mutated") is False,
        terminal.get("b2_started") is False,
        terminal.get("manuscript_revised") is False,
        readjudication.get("b11_terminal_status") == expected_terminal_status,
        b11_record.get("original_b1_code_freeze_sha256")
        == expected_b1_freeze_sha256,
    )
    if not all(terminal_checks):
        _fail("predecessor terminal status or freeze cross-check failed")

    return {
        "zip_sha256": observed_zip_sha256,
        "member_count": expected_member_count,
        "checksum_count": len(records),
        "crc_verified_member_count": expected_member_count,
        "member_set_sha256": digest_json(sorted(records)),
        "member_hash_tree_sha256": digest_json(records),
        "b1_freeze": b1_freeze,
        "b11_freeze": b11_freeze,
        "terminal_status": expected_terminal_status,
        "read_only_verification": require_read_only,
        "archive_extracted": False,
        "predecessor_code_executed": False,
        "verified": True,
    }


def verify_checksum_evidence(
    evidence_zip: Path,
    *,
    expected_zip_sha256: str,
    expected_member_count: int,
    expected_checksum_count: int,
    expected_terminal_status: str | None = None,
    manifest_name: str = PREDECESSOR_MANIFEST_NAME,
    require_read_only: bool = True,
) -> dict[str, Any]:
    """Verify a complete immutable evidence ZIP and optional terminal status.

    This deliberately generic path is used for the D0.2 diagnostic evidence;
    it validates every CRC/member hash but never imports or executes any
    predecessor source.
    """

    path = Path(evidence_zip)
    _require_sha256(expected_zip_sha256, label="expected evidence ZIP SHA-256")
    if not path.is_file() or path.is_symlink():
        _fail(f"evidence ZIP is not a regular file: {path}")
    observed_zip_sha256 = sha256_file(path)
    if observed_zip_sha256 != expected_zip_sha256:
        _fail("evidence ZIP SHA-256 mismatch")
    manifest_name = _validated_relative_path(manifest_name, label="manifest name")
    try:
        with ZipFile(path, "r") as archive:
            infos = _validate_zip_infos(
                archive.infolist(),
                expected_member_count=expected_member_count,
                require_read_only=require_read_only,
            )
            if manifest_name not in infos:
                _fail(f"evidence archive is missing {manifest_name}")
            records = parse_sha256_manifest(
                archive.read(infos[manifest_name]),
                expected_count=expected_checksum_count,
            )
            if manifest_name in records or set(infos) != set(records) | {manifest_name}:
                _fail("evidence ZIP and checksum tree paths differ")
            for relative in sorted(records):
                if _hash_zip_member(archive, infos[relative]) != records[relative]:
                    _fail(f"evidence member checksum mismatch: {relative}")
            terminal = None
            if expected_terminal_status is not None:
                if B11_TERMINAL_MEMBER not in infos:
                    _fail("evidence archive lacks terminal_status.json")
                terminal = _strict_json(
                    archive.read(infos[B11_TERMINAL_MEMBER]),
                    label=B11_TERMINAL_MEMBER,
                )
                if terminal.get("terminal_status") != expected_terminal_status:
                    _fail("evidence terminal status mismatch")
    except (BadZipFile, KeyError, OSError, RuntimeError) as error:
        if isinstance(error, IntegrityError):
            raise
        raise IntegrityError(f"cannot verify evidence ZIP: {path}") from error
    return {
        "zip_sha256": observed_zip_sha256,
        "member_count": expected_member_count,
        "checksum_count": len(records),
        "crc_verified_member_count": expected_member_count,
        "member_set_sha256": digest_json(sorted(records)),
        "member_hash_tree_sha256": digest_json(records),
        "terminal_status": expected_terminal_status,
        "read_only_verification": require_read_only,
        "archive_extracted": False,
        "predecessor_code_executed": False,
        "verified": True,
    }


def capture_file_seal(path: Path) -> dict[str, Any]:
    """Capture an immutable-file seal for a later before/after comparison."""

    value = Path(path)
    if not value.is_file() or value.is_symlink():
        _fail(f"cannot seal non-regular file: {value}")
    return {
        "bytes": value.stat().st_size,
        "sha256": sha256_file(value),
    }


def verify_file_seal(path: Path, seal: Mapping[str, Any]) -> dict[str, Any]:
    observed = capture_file_seal(path)
    expected = {"bytes": seal.get("bytes"), "sha256": seal.get("sha256")}
    if observed != expected:
        _fail(f"immutable file changed: {Path(path)}")
    return {**observed, "verified": True}


def verify_preflight(
    handoff_root: Path,
    handoff_zip: Path,
    *,
    manuscript_path: Path | None = None,
    require_read_only: bool = True,
) -> dict[str, Any]:
    """Run the complete locked-input preflight without executing science."""

    root = Path(handoff_root)
    handoff = verify_handoff_bundle(
        root,
        handoff_zip,
        require_read_only=require_read_only,
    )
    predecessor_path = root.joinpath(
        *PurePosixPath(PREDECESSOR_ARCHIVE_RELATIVE_PATH).parts
    )
    predecessor = verify_predecessor_evidence(predecessor_path)
    d0_2_path = root.joinpath(*PurePosixPath(D0_2_ARCHIVE_RELATIVE_PATH).parts)
    d0_2 = verify_checksum_evidence(
        d0_2_path,
        expected_zip_sha256=EXPECTED_D0_2_ZIP_SHA256,
        expected_member_count=EXPECTED_D0_2_MEMBER_COUNT,
        expected_checksum_count=EXPECTED_D0_2_CHECKSUM_COUNT,
        expected_terminal_status=EXPECTED_D0_2_TERMINAL_STATUS,
    )
    manuscript = (
        capture_file_seal(manuscript_path)
        if manuscript_path is not None
        else None
    )
    return {
        "handoff": handoff,
        "b11_predecessor": predecessor,
        "d0_2_predecessor": d0_2,
        "manuscript_before": manuscript,
        "science_executed": False,
        "verified": True,
    }


__all__ = [
    "B1_FREEZE_MEMBER",
    "B11_FREEZE_MEMBER",
    "B11_TERMINAL_MEMBER",
    "D0_2_ARCHIVE_RELATIVE_PATH",
    "EXPECTED_B11_FREEZE_SHA256",
    "EXPECTED_B11_TERMINAL_STATUS",
    "EXPECTED_B1_FREEZE_SHA256",
    "EXPECTED_D0_2_CHECKSUM_COUNT",
    "EXPECTED_D0_2_MEMBER_COUNT",
    "EXPECTED_D0_2_TERMINAL_STATUS",
    "EXPECTED_D0_2_ZIP_SHA256",
    "EXPECTED_HANDOFF_CHECKSUM_COUNT",
    "EXPECTED_HANDOFF_ZIP_SHA256",
    "EXPECTED_PREDECESSOR_CHECKSUM_COUNT",
    "EXPECTED_PREDECESSOR_MEMBER_COUNT",
    "EXPECTED_PREDECESSOR_ZIP_SHA256",
    "HANDOFF_MANIFEST_NAME",
    "IntegrityError",
    "canonical_json",
    "capture_file_seal",
    "digest_json",
    "parse_sha256_manifest",
    "recompute_freeze_sha256",
    "render_sha256_manifest",
    "sha256_file",
    "verify_directory_checksum_tree",
    "verify_file_seal",
    "verify_freeze_record",
    "verify_handoff_bundle",
    "verify_checksum_evidence",
    "verify_predecessor_evidence",
    "verify_preflight",
]
