"""Create a deterministic SHA-256 manifest for the reproducibility bundle."""

from __future__ import annotations

import hashlib
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    excluded_parts = {".git", "__pycache__", "tmp"}
    files = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.name != "SHA256SUMS"
        and not excluded_parts.intersection(path.relative_to(root).parts)
    ]
    lines = [f"{digest(path)}  {path.relative_to(root).as_posix()}" for path in sorted(files)]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} entries")


if __name__ == "__main__":
    main()
