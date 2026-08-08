#!/usr/bin/env python3
"""Reproduce the five paper figures from immutable canonical export inputs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil

from matplotlib import font_manager


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _font_path(*, bold: bool) -> Path:
    variable = "PSC_FONT_BOLD" if bold else "PSC_FONT_REGULAR"
    override = os.environ.get(variable)
    if override:
        path = Path(override).expanduser().resolve()
    else:
        properties = font_manager.FontProperties(
            family="DejaVu Sans", weight="bold" if bold else "normal"
        )
        path = Path(font_manager.findfont(properties, fallback_to_default=True))
    if not path.is_file():
        raise FileNotFoundError(f"portable font resolution failed for {variable}: {path}")
    return path


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/figure_reproduction"),
        help="fresh output directory below build/",
    )
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    canonical = repository / "artifacts" / "canonical_paper_export"
    build_root = (repository / "build").resolve()
    output = (repository / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir.resolve()
    if not _inside(output, build_root):
        raise ValueError("--output-dir must resolve below the repository build directory")
    if output.exists():
        shutil.rmtree(output)
    working = output / "canonical_paper_export"
    shutil.copytree(canonical, working)

    generator_path = working / "paper" / "generators" / "generate_paper_figures.py"
    spec = importlib.util.spec_from_file_location("canonical_figure_generator", generator_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load canonical generator: {generator_path}")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    regular = _font_path(bold=False)
    bold = _font_path(bold=True)
    generator.FONT_PATH = regular
    generator.FONT_BOLD_PATH = bold

    displayed = {
        "F2": generator.generate_f2(working),
        "F4": generator.generate_f4(working),
        "F5a": generator.generate_f5a(working),
        "F5b": generator.generate_f5b(working),
        "F5c": generator.generate_f5c(working),
    }
    canonical_receipt = json.loads(
        (canonical / "paper" / "figure_generation_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    if displayed != canonical_receipt["displayed_canonical_fields"]:
        raise AssertionError("regenerated displayed values differ from canonical receipt")

    figures = sorted((working / "paper" / "figures").glob("*"))
    receipt = {
        "schema_version": "PUBLICATION_FIGURE_REPRODUCTION_V1",
        "source": "artifacts/canonical_paper_export",
        "scientific_values_changed": False,
        "font_regular": regular.name,
        "font_bold": bold.name,
        "displayed_canonical_fields": displayed,
        "outputs": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in figures
            if path.is_file()
        },
    }
    receipt_path = output / "figure_reproduction_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Reproduced 5 PNG/PDF figure pairs in {working / 'paper' / 'figures'}")
    print(f"Canonical displayed values: verified ({receipt_path})")


if __name__ == "__main__":
    main()

