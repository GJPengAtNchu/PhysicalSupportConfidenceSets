#!/usr/bin/env python3
"""Build the three independent conceptual Figure 1 panels from TikZ sources.

This is a presentation-only operation.  It requires ``pdflatex``, ``pdftops``,
and ``pdftoppm`` on ``PATH`` and writes only below the ignored ``build/``
directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_program(name: str) -> str:
    lookup = f"{name}.exe" if os.name == "nt" and not name.endswith(".exe") else name
    program = shutil.which(lookup)
    if program is None:
        raise FileNotFoundError(f"required program not found on PATH: {name}")
    return program


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/figure1_reproduction"),
    )
    parser.add_argument("--png-dpi", type=int, default=300)
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    build_root = (repository / "build").resolve()
    output = (repository / args.output_dir).resolve()
    try:
        output.relative_to(build_root)
    except ValueError as error:
        raise ValueError("--output-dir must resolve below the repository build directory") from error

    sources = (
        repository
        / "artifacts"
        / "canonical_paper_export"
        / "paper"
        / "figure_sources"
        / "figure1"
    )
    expected = {
        "conceptual_pipeline_panel_a.tex": "78be1cc51fb35934a273511a0dfb7e7633c03aa8b4e8ce165b01c14de32ca1d9",
        "conceptual_pipeline_panel_b.tex": "44896f0d100755e1ca1614d212233e0dbf8a14e5118c35deb70551fc72e689ee",
        "conceptual_pipeline_panel_c.tex": "0db4ea9855a5af139771544fdad1bad8184cd06e1f87d4eae1c295f91f734bf1",
    }
    for name, digest in expected.items():
        actual = sha256(sources / name)
        if actual != digest:
            raise AssertionError(f"Figure 1 source hash mismatch for {name}: {actual}")

    pdflatex = require_program("pdflatex")
    pdftops = require_program("pdftops")
    pdftoppm = require_program("pdftoppm")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    wrapper_template = r"""\documentclass[tikz,border=4pt]{standalone}
\pdfinfoomitdate=1
\pdfsuppressptexinfo=15
\pdftrailerid{}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{xcolor}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,calc,positioning,shapes.geometric}
\begin{document}
\input{%s}
\end{document}
"""

    products: dict[str, dict[str, str | int]] = {}
    for panel in ("a", "b", "c"):
        stem = f"conceptual_pipeline_panel_{panel}"
        source_copy = output / f"{stem}.tex"
        shutil.copyfile(sources / f"{stem}.tex", source_copy)
        wrapper = output / f"{stem}_standalone.tex"
        wrapper.write_text(wrapper_template % stem, encoding="utf-8", newline="\n")
        subprocess.run(
            [
                pdflatex,
                "-interaction=nonstopmode",
                "-halt-on-error",
                f"-output-directory={output}",
                f"-jobname={stem}",
                str(wrapper),
            ],
            cwd=output,
            check=True,
        )
        pdf = output / f"{stem}.pdf"
        eps = output / f"{stem}.eps"
        png = output / f"{stem}.png"
        subprocess.run([pdftops, "-eps", "-level3", str(pdf), str(eps)], check=True)
        subprocess.run(
            [pdftoppm, "-png", "-r", str(args.png_dpi), "-singlefile", str(pdf), str(output / stem)],
            check=True,
        )
        products[stem] = {
            suffix: sha256(output / f"{stem}.{suffix}")
            for suffix in ("pdf", "eps", "png")
        }
        for temporary in (
            output / f"{stem}.aux",
            output / f"{stem}.log",
            source_copy,
            wrapper,
        ):
            temporary.unlink(missing_ok=True)

    receipt = {
        "schema_version": "CONCEPTUAL_FIGURE_REPRODUCTION_V1",
        "scientific_experiment_run": False,
        "source_hashes": expected,
        "outputs": products,
    }
    (output / "figure1_reproduction_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Reproduced three independent Figure 1 panel triplets in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
