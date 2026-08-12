#!/usr/bin/env python3
"""Regenerate presentation-only manuscript figures from final stored evidence.

This script performs no scientific fitting, simulation, candidate evaluation, or
data mutation.  It verifies every input against a pinned SHA-256 digest, reads
the stored values, applies only deterministic plotting transformations, and
writes vector PDF/EPS plus 300 dpi PNG versions of the manuscript figures and
their independently placeable panels.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle


SCRIPT_PATH = Path(__file__).resolve()
REPOSITORY_ROOT = SCRIPT_PATH.parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "artifacts"
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "build" / "figure_reproduction"
DEFAULT_B1_ROOT = SOURCE_ROOT / "canonical_paper_export" / "b11_global" / "figure_data"


# These hashes are the immutable canonical/final evidence identities.  A mismatch
# is a hard failure: the renderer must never silently consume revised inputs.
SOURCE_INPUTS: dict[str, tuple[Path, str]] = {
    "original_summary": (
        SOURCE_ROOT
        / "canonical_paper_export"
        / "original_numerical"
        / "canonical_summary.json",
        "ad6fbed5f4dd5b3e72f059f1b9e256bee21ba2730ae0429e37eab8d968889f9f",
    ),
    "confirmatory_summary": (
        SOURCE_ROOT
        / "canonical_paper_export"
        / "original_numerical"
        / "figure_data"
        / "confirmatory_summary.csv",
        "ca70145f3206d7d44b6c8bdbfef32dec3d0208761047c37cca5e71ae4dc2ea79",
    ),
    "task_controls": (
        SOURCE_ROOT
        / "canonical_paper_export"
        / "original_numerical"
        / "figure_data"
        / "task_controls.csv",
        "a72171efdbc41f4bd9af2883426bda84fa3224fbcc4d4de4dacb90250c6ae795",
    ),
    "dictionary_collapse": (
        SOURCE_ROOT
        / "canonical_paper_export"
        / "original_numerical"
        / "figure_data"
        / "dictionary_collapse.csv",
        "32caf957e68bde51ead777c3ebed50dc9338beba547be8e49b0c1f8fecb3219b",
    ),
    "formal_response_library": (
        SOURCE_ROOT
        / "canonical_paper_export"
        / "formal_b2"
        / "figure_data"
        / "response_library_and_coherence.json",
        "b9723f054323efbb973502e26e4ebcc955c79e37d3038d9b91a0bbb3038c085f",
    ),
    "formal_representative_rows": (
        SOURCE_ROOT
        / "canonical_paper_export"
        / "formal_b2"
        / "figure_data"
        / "representative_case_rows.csv",
        "c870beb55baba2da05568352f1b1092b255b7dc5abecc50e9f0fc7e9abfc1542",
    ),
    "formal_plugin_counts": (
        SOURCE_ROOT
        / "canonical_paper_export"
        / "formal_b2"
        / "figure_data"
        / "plugin_false_precision.csv",
        "c22e403919dc63df23bcaa4bed01af44c3247dd3065d0ce39706ae888eb20a6c",
    ),
    "formal_case_rows": (
        SOURCE_ROOT
        / "canonical_paper_export"
        / "formal_b2"
        / "canonical_case_rows.csv",
        "5e2d8817d2ae306482bb734368bd1b74260c02bad2463e1c27c00beb3b8ed6eb",
    ),
}

B1_INPUT_HASHES = {
    "controller_results.csv": (
        "c1f9d342465fe116f7dfe2c796a6889e81e9467d5e1a193c4bde38585977f211"
    ),
    "exact_validation_metrics.csv": (
        "5e755f882ac8b492c93d2ca08690c58b6f6ea53df6852ea429efd69801b40edf"
    ),
}


# Okabe-Ito-inspired palette, with line styles and hatches carrying redundant
# encodings so that the figures remain interpretable in grayscale.
BLUE = "#0072B2"
SKY = "#56B4E9"
GREEN = "#009E73"
ORANGE = "#D55E00"
GOLD = "#E69F00"
PURPLE = "#CC79A7"
BLACK = "#1A1A1A"
MID_GRAY = "#7A7A7A"
LIGHT_GRAY = "#D6D6D6"
VERY_LIGHT_GRAY = "#F3F3F3"
WHITE = "#FFFFFF"


FIXED_TIMESTAMP = dt.datetime(2026, 8, 12, tzinfo=dt.timezone.utc)
PDF_METADATA = {
    "Creator": "regenerate_manuscript_figures.py",
    "Producer": "Matplotlib",
    "CreationDate": FIXED_TIMESTAMP,
    "ModDate": FIXED_TIMESTAMP,
}
PNG_METADATA = {"Software": "regenerate_manuscript_figures.py"}
PS_METADATA = {"Creator": "regenerate_manuscript_figures.py"}


def configure_matplotlib() -> None:
    matplotlib.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "mathtext.fontset": "dejavusans",
            "font.size": 8.0,
            "axes.titlesize": 9.0,
            "axes.titleweight": "bold",
            "axes.labelsize": 8.0,
            "axes.linewidth": 0.8,
            "xtick.labelsize": 7.0,
            "ytick.labelsize": 7.0,
            "legend.fontsize": 6.7,
            "figure.facecolor": WHITE,
            "axes.facecolor": WHITE,
            "savefig.facecolor": WHITE,
            "savefig.transparent": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "pdf.compression": 6,
            "path.simplify": False,
        }
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_hashes(inputs: dict[str, tuple[Path, str]]) -> None:
    failures: list[str] = []
    for label, (path, expected) in inputs.items():
        if not path.is_file():
            failures.append(f"{label}: missing {path}")
            continue
        actual = sha256(path)
        if actual != expected:
            failures.append(
                f"{label}: SHA-256 mismatch\n"
                f"  expected {expected}\n"
                f"  actual   {actual}\n"
                f"  path     {path}"
            )
    if failures:
        raise RuntimeError("Input verification failed:\n" + "\n".join(failures))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object in {path}")
    return value


def as_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"Not a serialized Boolean: {value!r}")


def write_figure_files(
    fig: plt.Figure,
    output_dir: Path,
    stem: str,
) -> tuple[Path, Path, Path]:
    """Write one drawing in the three publication/review formats.

    PDF and EPS are vector outputs.  PNG is a 300-dpi preview.  The fixed
    PostScript timestamp keeps the EPS bytes reproducible across reruns.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"{stem}.pdf"
    eps_path = output_dir / f"{stem}.eps"
    png_path = output_dir / f"{stem}.png"
    fig.savefig(pdf_path, format="pdf", metadata=PDF_METADATA)

    fig.savefig(
        png_path,
        format="png",
        dpi=300,
        metadata=PNG_METADATA,
    )

    # Derive EPS from the authoritative vector PDF.  Matplotlib's native
    # PostScript backend cannot represent alpha and therefore changes grid and
    # annotation appearance.  Poppler performs a deterministic Level-3 vector
    # conversion and keeps all three delivered formats visually aligned.
    pdftops = shutil.which("pdftops")
    if pdftops is None:
        raise RuntimeError("pdftops is required for the publication EPS export")
    subprocess.run(
        [pdftops, "-eps", "-level3", str(pdf_path), str(eps_path)],
        check=True,
    )
    return pdf_path, eps_path, png_path


def save_figure(
    fig: plt.Figure, output_dir: Path, stem: str
) -> tuple[Path, Path, Path]:
    paths = write_figure_files(fig, output_dir, stem)
    plt.close(fig)
    return paths


def assert_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise AssertionError(f"{label}: expected {expected!r}, found {actual!r}")


def style_axis(ax: plt.Axes, *, grid: bool = True) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(direction="out", length=3.0, width=0.7)
    if grid:
        ax.grid(True, color=LIGHT_GRAY, linewidth=0.55, alpha=0.65, zorder=0)


def build_information_mechanism(
    inputs: dict[str, tuple[Path, str]], output_dir: Path
) -> tuple[Path, ...]:
    summary = read_json(inputs["original_summary"][0])
    confirm = read_csv(inputs["confirmatory_summary"][0])
    task = read_csv(inputs["task_controls"][0])

    if len(confirm) != 6 or len(task) != 450:
        raise AssertionError("Unexpected continuous-theory figure-data row count")

    scales = np.array([float(row["s"]) for row in confirm])
    expected_scales = np.array([0.045, 0.055, 0.067, 0.082, 0.100, 0.122])
    if not np.array_equal(scales, expected_scales):
        raise AssertionError(f"Unexpected separation-scale grid: {scales}")

    jeffreys = np.array([float(row["jeffreys_mean"]) for row in confirm])
    ci_low = np.array([float(row["jeffreys_ci_lower"]) for row in confirm])
    ci_high = np.array([float(row["jeffreys_ci_upper"]) for row in confirm])
    affinity_deficit = np.array(
        [float(row["affinity_deficit_mean"]) for row in confirm]
    )

    fit = summary["scaling"]["jeffreys"]
    slope = float(fit["slope"])
    ci_slope_low = float(fit["bootstrap_ci_lower"])
    ci_slope_high = float(fit["bootstrap_ci_upper"])
    r_squared = float(fit["r_squared"])
    assert_close(slope, 5.935475127180808, "Jeffreys slope")
    assert_close(ci_slope_low, 5.924895368471667, "Jeffreys CI lower")
    assert_close(ci_slope_high, 5.946782653030155, "Jeffreys CI upper")
    assert_close(r_squared, 0.9999901714129696, "Jeffreys R-squared")

    task_metrics = summary["task_controls"]
    max_equal = float(task_metrics["maximum_equal_coefficient_residual"])
    max_identity_error = float(
        task_metrics["maximum_contrast_formula_relative_error"]
    )
    assert_close(max_equal, 6.823543062565653e-16, "equal-coefficient residual")
    assert_close(
        max_identity_error,
        7.0118895279354466e-15,
        "contrast identity relative error",
    )

    # The published presentation recipe anchors the theoretical s^6 line at
    # the midpoint stored scale (the fourth of six rows, s=0.082).  This is a
    # display reference only; no slope is estimated here.
    anchor_index = len(scales) // 2
    reference_x = np.geomspace(scales.min(), scales.max(), 160)
    reference_y = jeffreys[anchor_index] * (
        reference_x / scales[anchor_index]
    ) ** 6

    task_slice = [row for row in task if math.isclose(float(row["s"]), 0.1)]
    if len(task_slice) != 75:
        raise AssertionError(f"Expected 75 stored task rows at s=0.1, got {len(task_slice)}")
    grouped: dict[float, list[dict[str, str]]] = defaultdict(list)
    for row in task_slice:
        grouped[float(row["contrast"])].append(row)
    if sorted(grouped) != [0.0, 0.25, 0.5]:
        raise AssertionError(f"Unexpected task contrasts: {sorted(grouped)}")
    for rows in grouped.values():
        rows.sort(key=lambda row: float(row["phi"]))
        phis = [float(row["phi"]) for row in rows]
        if len(phis) != 25 or not math.isclose(phis[0], 0.0) or not math.isclose(
            phis[-1], 0.6
        ):
            raise AssertionError("Unexpected task orientation grid")

    # Each manuscript panel is drawn on its own canvas.  These are not crops of
    # a composite figure: the axes geometry is designed for independent LaTeX
    # subfigure placement, and panel identifiers/titles live in LaTeX.
    fig_left, ax_left = plt.subplots(figsize=(3.60, 3.05))
    fig_left.subplots_adjust(left=0.18, right=0.97, bottom=0.18, top=0.96)
    fig_right, ax_right = plt.subplots(figsize=(3.60, 3.05))
    fig_right.subplots_adjust(left=0.18, right=0.97, bottom=0.18, top=0.96)

    jeffreys_handle = ax_left.errorbar(
        scales,
        jeffreys,
        yerr=np.vstack([jeffreys - ci_low, ci_high - jeffreys]),
        fmt="o-",
        markersize=4.0,
        linewidth=1.55,
        elinewidth=0.8,
        capsize=2.0,
        color=BLUE,
        label="Jeffreys divergence",
        zorder=4,
    )
    affinity_handle, = ax_left.plot(
        scales,
        affinity_deficit,
        "s--",
        markersize=3.6,
        linewidth=1.35,
        color=ORANGE,
        label=r"Affinity deficit $1-A$",
        zorder=3,
    )
    reference_handle, = ax_left.plot(
        reference_x,
        reference_y,
        linestyle=":",
        linewidth=1.6,
        color=BLACK,
        label=r"Reference $\propto s^6$",
        zorder=2,
    )
    ax_left.set_xscale("log")
    ax_left.set_yscale("log")
    ax_left.set_xlabel(r"Separation scale $s$")
    ax_left.set_ylabel("Divergence / affinity deficit")
    ax_left.legend(
        [jeffreys_handle, reference_handle, affinity_handle],
        ["Jeffreys divergence", r"Reference $\propto s^6$", r"Affinity deficit $1-A$"],
        loc="upper left",
        frameon=False,
        handlelength=2.4,
    )
    ax_left.text(
        0.98,
        0.05,
        "Slope = 5.935\n"
        "95% paired-batch MC stability range\n"
        "[5.925, 5.947]\n"
        r"$R^2 = 0.99999$",
        transform=ax_left.transAxes,
        ha="right",
        va="bottom",
        fontsize=7.0,
        bbox={"boxstyle": "round,pad=0.28", "fc": WHITE, "ec": LIGHT_GRAY},
        zorder=8,
    )
    style_axis(ax_left)

    task_colors = {0.0: BLACK, 0.25: BLUE, 0.5: ORANGE}
    task_markers = {0.0: "o", 0.25: "^", 0.5: "s"}
    task_labels = {
        0.0: r"Equal coefficients ($d=0$)",
        0.25: r"Unequal ($d=0.25$)",
        0.5: r"Unequal ($d=0.5$)",
    }
    for contrast in sorted(grouped):
        rows = grouped[contrast]
        phi = np.array([float(row["phi"]) for row in rows])
        numerical = np.array([float(row["numerical_residual"]) for row in rows])
        analytical = np.array([float(row["analytic_residual"]) for row in rows])
        ax_right.plot(
            phi,
            numerical,
            color=task_colors[contrast],
            marker=task_markers[contrast],
            markevery=2,
            markersize=3.1,
            linewidth=1.5,
            label=task_labels[contrast],
            zorder=4,
        )
        if contrast > 0:
            ax_right.plot(
                phi,
                analytical,
                color=task_colors[contrast],
                linestyle="--",
                linewidth=0.9,
                alpha=0.75,
                zorder=3,
            )

    handles, labels = ax_right.get_legend_handles_labels()
    handles.append(Line2D([0], [0], color=MID_GRAY, linestyle="--", linewidth=1.0))
    labels.append("Analytical identity")
    ax_right.legend(handles, labels, loc="upper left", frameon=False)
    ax_right.set_xlim(-0.01, 0.61)
    ax_right.set_ylim(-0.00125, 0.0250)
    ax_right.set_xlabel(r"Orientation perturbation $\phi$")
    ax_right.set_ylabel("Coefficient-profiled deployment residual")
    style_axis(ax_right)

    outputs = list(
        save_figure(
            fig_left,
            output_dir,
            "information_mechanism_panel_a",
        )
    )
    outputs.extend(
        save_figure(
            fig_right,
            output_dir,
            "information_mechanism_panel_b",
        )
    )
    return tuple(outputs)


def build_collapse_diagnostic(
    inputs: dict[str, tuple[Path, str]], output_dir: Path
) -> tuple[Path, Path, Path]:
    summary = read_json(inputs["original_summary"][0])
    rows = read_csv(inputs["dictionary_collapse"][0])
    if len(rows) != 10:
        raise AssertionError(f"Expected 10 stored collapse budgets, got {len(rows)}")

    budgets = np.array([float(row["budget"]) for row in rows])
    spreads = np.array([float(row["spread"]) for row in rows])
    expected_budgets = np.array([0.25, 0.5, 1, 2, 4, 8, 16, 32, 64, 128])
    if not np.array_equal(budgets, expected_budgets):
        raise AssertionError(f"Unexpected collapse budget grid: {budgets}")

    transition_budgets = np.array(summary["gate_collapse"]["transition_budgets"])
    transition_mask = np.isin(budgets, transition_budgets)
    median_spread = float(summary["gate_collapse"]["median_vertical_spread"])
    tolerance = float(summary["failed_frozen_criterion"]["threshold"])
    if bool(summary["failed_frozen_criterion"]["pass"]):
        raise AssertionError("Stored collapse criterion unexpectedly marked as passed")
    assert_close(median_spread, 0.016697583490912993, "collapse median")
    assert_close(tolerance, 0.015, "collapse tolerance")
    assert_close(float(np.median(spreads[transition_mask])), median_spread, "derived median")

    fig, ax = plt.subplots(figsize=(4.75, 3.25))
    fig.subplots_adjust(left=0.15, right=0.97, bottom=0.17, top=0.76)
    ax.axvspan(4, 64, color=VERY_LIGHT_GRAY, zorder=0)
    ax.plot(
        budgets,
        spreads,
        color=PURPLE,
        marker="o",
        markersize=3.8,
        linewidth=1.65,
        label="Across separation scales",
        zorder=4,
    )
    ax.scatter(
        budgets[transition_mask],
        spreads[transition_mask],
        s=30,
        facecolor=WHITE,
        edgecolor=PURPLE,
        linewidth=1.1,
        zorder=5,
        label="Transition budgets",
    )
    ax.axhline(
        tolerance,
        color=ORANGE,
        linestyle="--",
        linewidth=1.35,
        label="Prespecified tolerance = 0.015",
        zorder=2,
    )
    ax.hlines(
        median_spread,
        xmin=transition_budgets.min(),
        xmax=transition_budgets.max(),
        color=BLACK,
        linestyle=":",
        linewidth=1.25,
        label="Transition median = 0.0167",
        zorder=3,
    )
    ax.set_xscale("log")
    ax.set_xlim(0.20, 160)
    ax.set_ylim(0, 0.030)
    ax.set_xlabel(r"Orientation-information scale $I_D=Ns^6$")
    ax.set_ylabel(r"Vertical spread across $s$")
    ax.set_title("Across-scale collapse diagnostic", loc="left", pad=31)
    ax.legend(loc="upper left", frameon=False, ncol=1)
    ax.text(
        0.01,
        1.015,
        r"Transition median 0.0167 $>$ tolerance 0.015; criterion narrowly missed",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=6.4,
        zorder=8,
    )
    style_axis(ax)
    return save_figure(fig, output_dir, "collapse_diagnostic")


DISPLAY_LABELS = {
    "FINE": "Fine",
    "SECTOR_SAFE": "Group /\nsector",
    "SUPPORT_AMBIGUOUS": "Support\nambiguity",
    "ABSENT_ABOVE_BETA_MIN": "Absent at\nrepresented\nscale",
    "ABSTAIN": "Abstain",
}


def build_four_region_application(
    inputs: dict[str, tuple[Path, str]], output_dir: Path
) -> tuple[Path, ...]:
    library = read_json(inputs["formal_response_library"][0])
    representative_rows = read_csv(inputs["formal_representative_rows"][0])
    case_rows = read_csv(inputs["formal_case_rows"][0])
    plugin_counts = read_csv(inputs["formal_plugin_counts"][0])

    responses = library["response_library"]
    coherence = np.asarray(library["coherence_matrix"], dtype=float)
    sensors = np.asarray(library["sensor_locations"], dtype=float)
    if len(responses) != 12 or coherence.shape != (12, 12) or len(sensors) != 16:
        raise AssertionError("Unexpected Formal-B2 response-library dimensions")
    if library["candidate_count"] != 216 or library["dictionary_state_count"] != 72:
        raise AssertionError("Unexpected Formal-B2 bank dimensions")
    if not np.allclose(coherence, np.abs(coherence.T), atol=1.0e-14):
        raise AssertionError("Stored coherence matrix is not symmetric")

    representative = [
        row
        for row in representative_rows
        if row["case_id"] == "FORMAL_WEAK_C_PRESENT_P01"
    ]
    if len(representative) != 1:
        raise AssertionError("Expected one frozen weak-C representative row")
    representative = representative[0]
    if representative["scene"] != "WEAK_C_PRESENT":
        raise AssertionError("Representative scene mismatch")

    eligible = [
        row
        for row in case_rows
        if row["scene"] == "WEAK_C_PRESENT"
        and as_bool(row["oracle_complete"])
        and row["oracle_B"] == "SECTOR_SAFE"
        and row["oracle_C"] == "SUPPORT_AMBIGUOUS"
    ]
    eligible.sort(key=lambda row: int(row["launch_index"]))
    expected_profiles = ["P01", "P02", "P03", "P04", "P06"]
    profile_ids = [row["case_id"].rsplit("_", 1)[-1] for row in eligible]
    if profile_ids != expected_profiles:
        raise AssertionError(f"Unexpected eligible weak-C profiles: {profile_ids}")
    b_events = [row["plugin_B"] == "FINE" for row in eligible]
    c_events = [row["plugin_C"] != "SUPPORT_AMBIGUOUS" for row in eligible]
    if not all(b_events) or not all(c_events):
        raise AssertionError("Stored case rows do not support the two 5/5 event rows")

    aggregate = {row["metric"]: row for row in plugin_counts}
    for metric in ("plugin_B_false_FINE", "plugin_C_false_certainty"):
        row = aggregate[metric]
        if int(row["numerator"]) != 5 or int(row["denominator"]) != 5:
            raise AssertionError(f"Unexpected aggregate for {metric}: {row}")

    # Draw the four application panels on four independent canvases.  The
    # manuscript supplies panel letters and titles through subcaptions.
    fig_response, ax_response = plt.subplots(figsize=(3.85, 3.05))
    fig_response.subplots_adjust(left=0.16, right=0.975, bottom=0.18, top=0.86)
    fig_coherence, ax_coherence = plt.subplots(figsize=(3.55, 3.35))
    fig_coherence.subplots_adjust(left=0.16, right=0.82, bottom=0.19, top=0.97)
    fig_table, ax_table = plt.subplots(figsize=(3.85, 2.45))
    fig_table.subplots_adjust(left=0.01, right=0.99, bottom=0.02, top=0.99)
    fig_dots, ax_dots = plt.subplots(figsize=(3.55, 2.65))
    fig_dots.subplots_adjust(left=0.27, right=0.94, bottom=0.21, top=0.97)

    region_colors = {"A": BLUE, "B": ORANGE, "C": GREEN, "D": PURPLE}
    line_styles = ["-", "--", "-.", ":"]
    markers = ["o", "s", "^", "D"]
    for index, record in enumerate(responses):
        region = record["region"]
        within_region = sum(
            1
            for earlier in responses[:index]
            if earlier["region"] == region
        )
        values = np.asarray(record["values"], dtype=float)
        if values.shape != sensors.shape:
            raise AssertionError(f"Response length mismatch for {record['atom_id']}")
        ax_response.plot(
            sensors,
            values,
            color=region_colors[region],
            linestyle=line_styles[within_region % len(line_styles)],
            marker=markers[within_region % len(markers)],
            markevery=4,
            markersize=2.6,
            linewidth=1.15,
            label=record["atom_id"],
        )
    ax_response.axhline(0, color=LIGHT_GRAY, linewidth=0.7, zorder=0)
    ax_response.set_xlabel("Sensor location")
    ax_response.set_ylabel("Response amplitude")
    response_keys = [
        (0.00, "A: A1 A2", BLUE),
        (0.22, "B: B1 B2 B3 B4", ORANGE),
        (0.57, "C: C1 C2 C3", GREEN),
        (0.80, "D: D1 D2 D3", PURPLE),
    ]
    for key_x, key_text, key_color in response_keys:
        ax_response.text(
            key_x,
            1.015,
            key_text,
            transform=ax_response.transAxes,
            ha="left",
            va="bottom",
            fontsize=6.7,
            fontweight="bold",
            color=key_color,
        )
    style_axis(ax_response)

    cell_edges = np.arange(13, dtype=float) - 0.5
    image = ax_coherence.pcolormesh(
        cell_edges,
        cell_edges,
        np.abs(coherence),
        vmin=0,
        vmax=1,
        cmap="cividis",
        shading="flat",
        rasterized=False,
    )
    ax_coherence.set_xlim(-0.5, 11.5)
    ax_coherence.set_ylim(11.5, -0.5)
    ax_coherence.set_aspect("equal")
    atom_labels = [record["atom_id"] for record in responses]
    ax_coherence.set_xticks(np.arange(12), atom_labels, rotation=45, ha="right")
    ax_coherence.set_yticks(np.arange(12), atom_labels)
    for boundary in (1.5, 5.5, 8.5):
        ax_coherence.axvline(boundary, color=WHITE, linewidth=2.2)
        ax_coherence.axvline(boundary, color=BLACK, linewidth=0.75)
        ax_coherence.axhline(boundary, color=WHITE, linewidth=2.2)
        ax_coherence.axhline(boundary, color=BLACK, linewidth=0.75)
    region_ranges = {"A": (0, 2), "B": (2, 6), "C": (6, 9), "D": (9, 12)}
    for region, (start, stop) in region_ranges.items():
        ax_coherence.add_patch(
            Rectangle(
                (start - 0.5, start - 0.5),
                stop - start,
                stop - start,
                fill=False,
                edgecolor=region_colors[region],
                linewidth=1.45,
            )
        )
        ax_coherence.text(
            start - 0.31,
            start - 0.12,
            region,
            ha="left",
            va="top",
            fontsize=7.0,
            fontweight="bold",
            color=WHITE,
            bbox={"boxstyle": "square,pad=0.15", "fc": region_colors[region], "ec": WHITE},
        )
    colorbar = fig_coherence.colorbar(
        image,
        ax=ax_coherence,
        fraction=0.047,
        pad=0.035,
    )
    if colorbar.solids is not None:
        colorbar.solids.set_rasterized(False)
    colorbar.set_label(r"$|\langle d_i,d_j\rangle|$", fontsize=7.0)
    colorbar.ax.tick_params(labelsize=6.2, length=2)

    ax_table.axis("off")
    rows = []
    for region in ("A", "B", "C", "D"):
        aeb = DISPLAY_LABELS[representative[f"stage_a_controller_{region}"]]
        oracle = DISPLAY_LABELS[representative[f"oracle_{region}"]]
        plugin_key = representative[f"plugin_{region}"]
        plugin = DISPLAY_LABELS[plugin_key]
        if region == "C" and plugin_key == "ABSENT_ABOVE_BETA_MIN":
            plugin = "Absent\n(definite)"
        rows.append([region, aeb, oracle, plugin])
    table = ax_table.table(
        cellText=rows,
        colLabels=["Region", "AEB", "Exhaustive\nsame-bank", "Point-valued\nplug-in"],
        colWidths=[0.14, 0.26, 0.32, 0.28],
        cellLoc="center",
        loc="upper center",
        bbox=[0.025, 0.06, 0.96, 0.88],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(6.7)
    for (row_index, col_index), cell in table.get_celld().items():
        cell.set_edgecolor(WHITE)
        cell.set_linewidth(1.2)
        if row_index == 0:
            cell.set_facecolor(BLACK)
            cell.get_text().set_color(WHITE)
            cell.get_text().set_fontweight("bold")
        else:
            cell.set_facecolor(VERY_LIGHT_GRAY if row_index % 2 else "#E8E8E8")
            if col_index == 0:
                cell.get_text().set_fontweight("bold")
                cell.get_text().set_color(region_colors[rows[row_index - 1][0]])
    # Point-valued plug-in cells for B and C are the only highlighted disagreements.
    table[(2, 3)].set_facecolor("#F6D6C8")
    table[(3, 3)].set_facecolor("#F6D6C8")
    table[(2, 3)].get_text().set_fontweight("bold")
    table[(3, 3)].get_text().set_fontweight("bold")

    x = np.arange(1, 6)
    y_b = np.ones(5)
    y_c = np.zeros(5)
    ax_dots.scatter(
        x,
        y_b,
        s=64,
        marker="o",
        facecolor=ORANGE,
        edgecolor=BLACK,
        linewidth=0.75,
        zorder=4,
        label="Observed event",
    )
    ax_dots.scatter(
        x,
        y_c,
        s=64,
        marker="s",
        facecolor=BLUE,
        edgecolor=BLACK,
        linewidth=0.75,
        zorder=4,
    )
    ax_dots.set_xlim(0.45, 6.15)
    ax_dots.set_ylim(-0.55, 1.55)
    # Present the five eligible profiles as reader-facing indices. Their
    # immutable internal identities remain asserted above and in provenance,
    # but are not manuscript terminology.
    ax_dots.set_xticks(x, [str(index) for index in x])
    ax_dots.set_yticks([1, 0], ["B overprecision", "C false certainty"])
    ax_dots.set_xlabel("Eligible completed weak-C profile")
    ax_dots.text(5.42, 1, "5/5", va="center", ha="left", fontweight="bold", color=ORANGE)
    ax_dots.text(5.42, 0, "5/5", va="center", ha="left", fontweight="bold", color=BLUE)
    style_axis(ax_dots)
    ax_dots.grid(axis="x", color=LIGHT_GRAY, linewidth=0.55, alpha=0.75)
    ax_dots.grid(axis="y", color=LIGHT_GRAY, linewidth=0.55, alpha=0.75)

    outputs = list(
        save_figure(
            fig_response,
            output_dir,
            "four_region_application_panel_a",
        )
    )
    outputs.extend(
        save_figure(
            fig_coherence,
            output_dir,
            "four_region_application_panel_b",
        )
    )
    outputs.extend(
        save_figure(
            fig_table,
            output_dir,
            "four_region_application_panel_c",
        )
    )
    outputs.extend(
        save_figure(
            fig_dots,
            output_dir,
            "four_region_application_panel_d",
        )
    )
    return tuple(outputs)


def build_b1_inputs(b1_root: Path) -> dict[str, tuple[Path, str]]:
    return {
        "b1_controller_results": (
            b1_root / "controller_results.csv",
            B1_INPUT_HASHES["controller_results.csv"],
        ),
        "b1_exact_validation": (
            b1_root / "exact_validation_metrics.csv",
            B1_INPUT_HASHES["exact_validation_metrics.csv"],
        ),
    }


def categorize_b1(output: str, oracle_label: str) -> str:
    expected_output = {
        "ORACLE_FINE": "FINE",
        "ORACLE_SECTOR": "SECTOR_SAFE",
        "ORACLE_AMBIGUOUS": "AMBIGUOUS",
    }[oracle_label]
    if output == "ABSTAIN":
        return "Abstain"
    if output == expected_output:
        return "Exact reference match"
    if oracle_label == "ORACLE_FINE" and output == "SECTOR_SAFE":
        return "Safely coarser"
    return "Unsafe finer / unsupported"


def build_global_query_resolution(
    inputs: dict[str, tuple[Path, str]], output_dir: Path
) -> tuple[Path, ...]:
    controller = read_csv(inputs["b1_controller_results"][0])
    validation = read_csv(inputs["b1_exact_validation"][0])
    if len(controller) != 324 or len(validation) != 54:
        raise AssertionError(
            f"Unexpected B1.1 row counts: controller={len(controller)}, validation={len(validation)}"
        )

    oracle_by_key: dict[tuple[str, str], str] = {}
    for row in validation:
        key = (row["case_id"], row["profile"])
        if key in oracle_by_key:
            raise AssertionError(f"Duplicate exhaustive-reference key: {key}")
        oracle_by_key[key] = row["oracle_label"]

    enriched: list[dict[str, Any]] = []
    for row in controller:
        key = (row["case_id"], row["profile"])
        if key not in oracle_by_key:
            raise AssertionError(f"Controller row lacks exhaustive reference: {key}")
        oracle_label = oracle_by_key[key]
        enriched.append(
            {
                "budget": float(row["budget_fraction"]),
                "output": row["output"],
                "oracle": oracle_label,
                "category": categorize_b1(row["output"], oracle_label),
            }
        )

    budgets = sorted({row["budget"] for row in enriched})
    expected_budgets = [0.10, 0.20, 0.35, 0.50, 0.75, 1.00]
    if budgets != expected_budgets:
        raise AssertionError(f"Unexpected B1.1 budget grid: {budgets}")

    categories = [
        "Exact reference match",
        "Safely coarser",
        "Abstain",
        "Unsafe finer / unsupported",
    ]
    counts: dict[float, Counter[str]] = {}
    for budget in budgets:
        selected = [row for row in enriched if row["budget"] == budget]
        if len(selected) != 54:
            raise AssertionError(f"Budget {budget} has {len(selected)} rows, expected 54")
        counts[budget] = Counter(row["category"] for row in selected)

    expected_counts = {
        0.10: (25, 0, 29, 0),
        0.20: (27, 0, 27, 0),
        0.35: (31, 0, 23, 0),
        0.50: (38, 3, 13, 0),
        0.75: (52, 2, 0, 0),
        1.00: (54, 0, 0, 0),
    }
    for budget, expected in expected_counts.items():
        actual = tuple(counts[budget][category] for category in categories)
        if actual != expected:
            raise AssertionError(
                f"B1.1 category mismatch at budget {budget}: expected {expected}, found {actual}"
            )

    recovery: dict[float, dict[str, tuple[int, int]]] = {}
    for budget in (0.50, 0.75):
        selected = [row for row in enriched if row["budget"] == budget]
        ambiguous = [row for row in selected if row["oracle"] == "ORACLE_AMBIGUOUS"]
        fine = [row for row in selected if row["oracle"] == "ORACLE_FINE"]
        recovery[budget] = {
            "Ambiguity": (
                sum(row["output"] == "AMBIGUOUS" for row in ambiguous),
                len(ambiguous),
            ),
            "Fine": (sum(row["output"] == "FINE" for row in fine), len(fine)),
        }
    expected_recovery = {
        0.50: {"Ambiguity": (33, 34), "Fine": (0, 7)},
        0.75: {"Ambiguity": (34, 34), "Fine": (5, 7)},
    }
    if recovery != expected_recovery:
        raise AssertionError(f"B1.1 recovery mismatch: {recovery}")

    # Use independent canvases so LaTeX can place and caption each panel without
    # inheriting a composite subplot geometry.
    fig_stack, ax_stack = plt.subplots(figsize=(4.25, 3.25))
    fig_stack.subplots_adjust(left=0.15, right=0.98, bottom=0.18, top=0.76)
    fig_recovery, ax_recovery = plt.subplots(figsize=(3.30, 3.05))
    fig_recovery.subplots_adjust(left=0.23, right=0.95, bottom=0.19, top=0.97)

    x = np.arange(len(budgets))
    category_colors = {
        "Exact reference match": BLUE,
        "Safely coarser": GREEN,
        "Abstain": LIGHT_GRAY,
        "Unsafe finer / unsupported": ORANGE,
    }
    category_hatches = {
        "Exact reference match": "",
        "Safely coarser": "///",
        "Abstain": "..",
        "Unsafe finer / unsupported": "xxx",
    }
    bottoms = np.zeros(len(budgets))
    for category in categories:
        heights = np.array([counts[budget][category] for budget in budgets])
        ax_stack.bar(
            x,
            heights,
            bottom=bottoms,
            width=0.72,
            color=category_colors[category],
            edgecolor=BLACK,
            linewidth=0.55,
            hatch=category_hatches[category],
            label=category,
            zorder=3,
        )
        for index, height in enumerate(heights):
            if height <= 0:
                continue
            y = bottoms[index] + height / 2
            text_color = WHITE if category == "Exact reference match" else BLACK
            ax_stack.text(
                x[index],
                y,
                str(int(height)),
                ha="center",
                va="center",
                fontsize=6.7,
                fontweight="bold",
                color=text_color,
                zorder=5,
            )
        bottoms += heights

    # A visible zero row makes the unsafe category explicit even though its
    # bars have exactly zero height at every saved budget.
    for index in range(len(budgets)):
        ax_stack.text(
            x[index],
            56.2,
            "0",
            ha="center",
            va="bottom",
            fontsize=5.8,
            color=ORANGE,
            fontweight="bold",
        )
    ax_stack.set_xticks(x, [f"{budget:.2f}" for budget in budgets])
    ax_stack.set_ylim(0, 59.5)
    ax_stack.set_ylabel("Reporting traces (n=54)")
    ax_stack.set_xlabel("Query-budget fraction")
    legend_handles = [
        Patch(
            facecolor=category_colors[category],
            edgecolor=BLACK,
            hatch=category_hatches[category],
            label=category,
        )
        for category in categories
    ]
    ax_stack.legend(
        handles=legend_handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.015),
        ncol=2,
        frameon=False,
        columnspacing=0.8,
        handlelength=1.7,
        fontsize=6.2,
    )
    style_axis(ax_stack)

    outcomes = ["Ambiguity", "Fine"]
    y = np.arange(len(outcomes))
    bar_height = 0.30
    budget_styles = [(0.50, BLUE, -bar_height / 2), (0.75, GOLD, bar_height / 2)]
    for budget, color, offset in budget_styles:
        fractions = np.array(
            [
                recovery[budget][outcome][0] / recovery[budget][outcome][1]
                for outcome in outcomes
            ]
        )
        bars = ax_recovery.barh(
            y + offset,
            fractions,
            height=bar_height * 0.86,
            color=color,
            edgecolor=BLACK,
            linewidth=0.55,
            label=f"Budget {budget:.2f}",
            zorder=3,
        )
        for outcome, fraction, bar in zip(outcomes, fractions, bars):
            numerator, denominator = recovery[budget][outcome]
            text_x = max(fraction + 0.025, 0.035)
            ax_recovery.text(
                text_x,
                bar.get_y() + bar.get_height() / 2,
                f"{numerator}/{denominator}",
                ha="left",
                va="center",
                fontsize=6.8,
                fontweight="bold",
                color=BLACK,
            )
    ax_recovery.set_yticks(y, outcomes)
    ax_recovery.invert_yaxis()
    ax_recovery.set_xlim(0, 1.18)
    ax_recovery.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax_recovery.set_xticklabels(["0", ".25", ".50", ".75", "1"])
    ax_recovery.set_xlabel("Reference-specific recovery rate")
    ax_recovery.legend(loc="center right", frameon=False)
    style_axis(ax_recovery)

    outputs = list(
        save_figure(
            fig_stack,
            output_dir,
            "global_query_resolution_panel_a",
        )
    )
    outputs.extend(
        save_figure(
            fig_recovery,
            output_dir,
            "global_query_resolution_panel_b",
        )
    )
    return tuple(outputs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Destination for independent PDF/EPS/PNG panels (default: build/figure_reproduction).",
    )
    parser.add_argument(
        "--b1-root",
        type=Path,
        default=DEFAULT_B1_ROOT,
        help="Canonical B1.1 figure-data directory containing controller and exact-validation rows.",
    )
    arguments = parser.parse_args()
    output_dir = arguments.output_dir.resolve()
    b1_root = arguments.b1_root.resolve()
    build_root = (REPOSITORY_ROOT / "build").resolve()
    try:
        output_dir.relative_to(build_root)
    except ValueError as error:
        raise ValueError("--output-dir must resolve below the repository build directory") from error

    configure_matplotlib()
    b1_inputs = build_b1_inputs(b1_root)
    all_inputs = {**SOURCE_INPUTS, **b1_inputs}
    verify_hashes(all_inputs)

    outputs: list[Path] = []
    outputs.extend(build_information_mechanism(all_inputs, output_dir))
    outputs.extend(build_collapse_diagnostic(all_inputs, output_dir))
    outputs.extend(build_four_region_application(all_inputs, output_dir))
    outputs.extend(build_global_query_resolution(all_inputs, output_dir))

    # Confirm that rendering did not alter any read-only scientific input.
    verify_hashes(all_inputs)

    print("Verified immutable inputs:")
    for label, (path, expected) in all_inputs.items():
        print(f"  {label}: {expected}  {path}")
    print("Generated presentation-only outputs:")
    for path in outputs:
        print(f"  {sha256(path)}  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
