#!/usr/bin/env python3
"""Deterministically render M0-B paper figures from canonical export data only."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


INK = "#17212B"
MUTED = "#5E6B75"
GRID = "#D8DEE4"
BG = "#FFFFFF"
BLUE = "#246BCE"
ORANGE = "#D97706"
GREEN = "#14805E"
PURPLE = "#7C4DCA"
RED = "#C43D4D"
FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONT_BOLD_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def font(size: int, bold: bool = False):
    path = FONT_BOLD_PATH if bold else FONT_PATH
    return ImageFont.truetype(str(path), size=size)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def save_png_pdf(image: Image.Image, png: Path, pdf: Path, title: str) -> None:
    png.parent.mkdir(parents=True, exist_ok=True)
    image.save(png, format="PNG", optimize=False, compress_level=9, dpi=(144, 144))
    width, height = image.size
    document = canvas.Canvas(
        str(pdf), pagesize=(float(width), float(height)), pageCompression=1, invariant=1
    )
    document.setTitle(title)
    document.setAuthor("M0-B canonical figure generator")
    document.drawImage(ImageReader(str(png)), 0, 0, width=width, height=height)
    document.showPage()
    document.save()


def draw_text_center(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, fnt, fill=INK) -> None:
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1] - (box[3] - box[1]) / 2), text, font=fnt, fill=fill)


def transform(value: float, low: float, high: float, start: float, end: float, log: bool) -> float:
    if log:
        value, low, high = math.log10(value), math.log10(low), math.log10(high)
    if high == low:
        return (start + end) / 2
    return start + (value - low) * (end - start) / (high - low)


def line_chart(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    series: list[tuple[str, list[tuple[float, float]], str, int]],
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    x_label: str,
    y_label: str,
    log_x: bool = False,
    log_y: bool = False,
    reference_y: tuple[float, str] | None = None,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=16, fill="#FBFCFD", outline=GRID, width=2)
    draw.text((x0 + 24, y0 + 18), title, font=font(25, True), fill=INK)
    left, top, right, bottom = x0 + 80, y0 + 78, x1 - 30, y1 - 72
    for i in range(5):
        px = left + i * (right - left) / 4
        py = top + i * (bottom - top) / 4
        draw.line((px, top, px, bottom), fill=GRID, width=1)
        draw.line((left, py, right, py), fill=GRID, width=1)
        xv = 10 ** (math.log10(x_range[0]) + i * (math.log10(x_range[1]) - math.log10(x_range[0])) / 4) if log_x else x_range[0] + i * (x_range[1] - x_range[0]) / 4
        yv = 10 ** (math.log10(y_range[1]) - i * (math.log10(y_range[1]) - math.log10(y_range[0])) / 4) if log_y else y_range[1] - i * (y_range[1] - y_range[0]) / 4
        draw_text_center(draw, (px, bottom + 22), f"{xv:.2g}", font(15), MUTED)
        draw.text((x0 + 8, py - 9), f"{yv:.2g}", font=font(15), fill=MUTED)
    draw.line((left, bottom, right, bottom), fill=INK, width=2)
    draw.line((left, top, left, bottom), fill=INK, width=2)
    if reference_y is not None:
        y_value, label = reference_y
        py = transform(y_value, y_range[0], y_range[1], bottom, top, log_y)
        draw.line((left, py, right, py), fill=RED, width=2)
        draw.text((right - 175, py - 24), label, font=font(14, True), fill=RED)
    legend_x = left + 8
    for label, points, color, width in series:
        coords = [
            (
                transform(x, x_range[0], x_range[1], left, right, log_x),
                transform(y, y_range[0], y_range[1], bottom, top, log_y),
            )
            for x, y in points
            if x_range[0] <= x <= x_range[1] and y_range[0] <= y <= y_range[1]
        ]
        if len(coords) > 1:
            draw.line(coords, fill=color, width=width, joint="curve")
        for px, py in coords:
            draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=color)
        if label:
            draw.line((legend_x, top + 8, legend_x + 24, top + 8), fill=color, width=4)
            draw.text((legend_x + 30, top - 3), label, font=font(14), fill=INK)
            legend_x += 30 + draw.textlength(label, font=font(14)) + 36
    draw_text_center(draw, ((left + right) / 2, y1 - 26), x_label, font(16), INK)
    draw.text((x0 + 12, top - 36), y_label, font=font(15), fill=INK)


def generate_f2(root: Path) -> dict:
    summary = json.loads((root / "original_numerical/canonical_summary.json").read_text(encoding="utf-8"))
    confirm = read_csv(root / "original_numerical/figure_data/confirmatory_summary.csv")
    gates = read_csv(root / "original_numerical/figure_data/gate_curves.csv")
    collapse = read_csv(root / "original_numerical/figure_data/dictionary_collapse.csv")
    threshold = float(summary["failed_frozen_criterion"]["threshold"])
    median_spread = float(summary["gate_collapse"]["median_vertical_spread"])
    image = Image.new("RGB", (2100, 760), BG)
    draw = ImageDraw.Draw(image)
    draw.text((42, 22), "Theorem-native three-gate information geometry", font=font(34, True), fill=INK)
    draw.text((42, 66), f"Pairwise diagnostics only · frozen status {summary['status']} · median {median_spread:.7f} > {threshold:.3f}", font=font(20), fill=RED)

    colors = {"parent": BLUE, "support": ORANGE, "dictionary": GREEN}
    gate_series = []
    for gate in ("parent", "support", "dictionary"):
        by_s: dict[float, list[tuple[float, float]]] = {}
        for row in gates:
            if row["gate"] == gate:
                by_s.setdefault(float(row["s"]), []).append((float(row["budget"]), float(row["primary"])))
        for idx, points in enumerate(sorted(by_s.items())):
            gate_series.append((gate if idx == 0 else "", sorted(points[1]), colors[gate], 3 if idx == 0 else 1))
    line_chart(draw, (30, 110, 700, 700), "(a) Separate pairwise gates", gate_series, (0.25, 64), (0, 1), "information budget", "primary", log_x=True)

    s_points_j = [(float(row["s"]), float(row["jeffreys_mean"])) for row in confirm]
    s_points_a = [(float(row["s"]), float(row["affinity_deficit_mean"])) for row in confirm]
    y_values = [y for _, y in s_points_j + s_points_a]
    line_chart(draw, (715, 110, 1385, 700), "(b) Sixth-order scaling", [("Jeffreys", s_points_j, BLUE, 4), ("Affinity deficit", s_points_a, ORANGE, 4)], (min(x for x, _ in s_points_j), max(x for x, _ in s_points_j)), (min(y_values) * 0.8, max(y_values) * 1.25), "collision scale s", "divergence", log_x=True, log_y=True)

    collapse_points = [(float(row["budget"]), float(row["spread"])) for row in collapse]
    line_chart(draw, (1400, 110, 2070, 700), "(c) Product-affinity collapse", [("vertical spread", collapse_points, PURPLE, 4)], (0.25, 64), (0, 0.03), "dictionary budget Ns⁶", "spread", log_x=True, reference_y=(threshold, f"frozen threshold {threshold:.3f}"))
    save_png_pdf(image, root / "paper/figures/theorem_native_three_gate.png", root / "paper/figures/theorem_native_three_gate.pdf", "Theorem-native three-gate information geometry")
    return {
        "status": {"canonical_field": "original_numerical/canonical_summary.json::$.status", "value": summary["status"]},
        "median_spread": {"canonical_field": "original_numerical/canonical_summary.json::$.gate_collapse.median_vertical_spread", "value": median_spread},
        "failed_threshold": {"canonical_field": "original_numerical/canonical_summary.json::$.failed_frozen_criterion.threshold", "value": threshold},
    }


def generate_f4(root: Path) -> dict:
    summary = json.loads((root / "b11_global/canonical_summary.json").read_text(encoding="utf-8"))
    rows = read_csv(root / "b11_global/figure_data/risk_resolution_yield_frontier.csv")
    metrics = [
        ("Non-abstain yield", "nonabstain_yield", BLUE),
        ("AMBIGUOUS recall", "ambiguous_recall", ORANGE),
        ("FINE recall", "fine_recall", GREEN),
        ("Safe nonambiguous", "safe_nonambiguous_rate", PURPLE),
    ]
    series = [(label, [(float(r["budget_fraction"]), float(r[key])) for r in rows], color, 5) for label, key, color in metrics]
    image = Image.new("RGB", (1600, 980), BG)
    draw = ImageDraw.Draw(image)
    draw.text((45, 24), "Finite-bank B1.1 global risk–resolution–yield frontier", font=font(34, True), fill=INK)
    draw.text((45, 70), f"{summary['completed_finite_bank_cases']} complete cases · {summary['sealed_global_controller_traces']} sealed global traces · empirical exact-finite-bank audit", font=font(20), fill=MUTED)
    line_chart(draw, (55, 120, 1545, 880), "Global controller across frozen query budgets", series, (0.1, 1.0), (0, 1), "budget fraction", "rate")
    for budget, label in [(0.5, "0.50"), (0.75, "0.75")]:
        px = transform(budget, 0.1, 1.0, 135, 1515, False)
        draw.line((px, 198, px, 808), fill=RED, width=2)
        draw.text((px + 7, 810), label, font=font(16, True), fill=RED)
    draw.text((55, 920), "Scope: global finite-bank controller; no local-map, continuous-space, or exact selective-risk claim.", font=font(18), fill=INK)
    save_png_pdf(image, root / "paper/figures/b11_global_frontier.png", root / "paper/figures/b11_global_frontier.pdf", "B1.1 global finite-bank frontier")
    return {
        "complete_case_count": {"canonical_field": "b11_global/canonical_summary.json::$.completed_finite_bank_cases", "value": summary["completed_finite_bank_cases"]},
        "sealed_trace_count": {"canonical_field": "b11_global/canonical_summary.json::$.sealed_global_controller_traces", "value": summary["sealed_global_controller_traces"]},
    }


def generate_f5a(root: Path) -> dict:
    data = json.loads((root / "formal_b2/figure_data/response_library_and_coherence.json").read_text(encoding="utf-8"))
    image = Image.new("RGB", (1900, 920), BG)
    draw = ImageDraw.Draw(image)
    region_count = len({atom["region"] for atom in data["response_library"]})
    response_count = len(data["response_library"])
    draw.text((45, 24), f"Frozen {region_count}-region finite-bank application", font=font(34, True), fill=INK)
    draw.text((45, 70), f"{response_count} response atoms · {data['dictionary_state_count']} dictionary states · {data['candidate_count']} candidate explanations · synthetic application only", font=font(20), fill=MUTED)
    colors = {"A": BLUE, "B": ORANGE, "C": GREEN, "D": PURPLE}
    response_series = []
    sensors = data["sensor_locations"]
    for atom in data["response_library"]:
        response_series.append((atom["region"] if atom["atom_id"].endswith("1") else "", list(zip(sensors, atom["values"])), colors[atom["region"]], 3))
    all_values = [v for atom in data["response_library"] for v in atom["values"]]
    line_chart(draw, (45, 125, 1025, 840), "(a) Response library", response_series, (min(sensors), max(sensors)), (min(all_values) - 0.05, max(all_values) + 0.05), "sensor location", "response")

    x0, y0, x1, y1 = 1060, 125, 1855, 840
    draw.rounded_rectangle((x0, y0, x1, y1), radius=16, fill="#FBFCFD", outline=GRID, width=2)
    draw.text((x0 + 24, y0 + 18), "(b) Absolute coherence", font=font(25, True), fill=INK)
    matrix = data["coherence_matrix"]
    n = len(matrix)
    cell = 48
    left, top = x0 + 92, y0 + 88
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            v = min(1.0, max(0.0, abs(float(value))))
            color = (int(245 - 195 * v), int(248 - 120 * v), int(252 - 35 * v))
            draw.rectangle((left + j * cell, top + i * cell, left + (j + 1) * cell, top + (i + 1) * cell), fill=color, outline="#FFFFFF")
    for idx, atom in enumerate(data["response_library"]):
        draw_text_center(draw, (left + idx * cell + cell / 2, top - 18), atom["atom_id"], font(12), INK)
        draw.text((left - 48, top + idx * cell + 14), atom["atom_id"], font=font(12), fill=INK)
    draw.text((x0 + 92, y1 - 54), "lighter = lower |inner product|; darker = higher", font=font(16), fill=MUTED)
    save_png_pdf(image, root / "paper/figures/formal_b2_response_library.png", root / "paper/figures/formal_b2_response_library.pdf", "Formal B2 response library and coherence")
    return {
        "region_count": {"canonical_field": "formal_b2/figure_data/response_library_and_coherence.json::$.response_library[*].region (unique)", "value": region_count},
        "response_atom_count": {"canonical_field": "formal_b2/figure_data/response_library_and_coherence.json::$.response_library (length)", "value": response_count},
        "dictionary_state_count": {"canonical_field": "formal_b2/figure_data/response_library_and_coherence.json::$.dictionary_state_count", "value": data["dictionary_state_count"]},
        "candidate_explanation_count": {"canonical_field": "formal_b2/figure_data/response_library_and_coherence.json::$.candidate_count", "value": data["candidate_count"]},
    }


def generate_f5b(root: Path) -> dict:
    summary = json.loads((root / "formal_b2/canonical_merged_summary.json").read_text(encoding="utf-8"))
    representatives = json.loads((root / "formal_b2/representative_examples.json").read_text(encoding="utf-8"))
    empty_profile = json.loads((root / "formal_b2/empty_profile_disclosure.json").read_text(encoding="utf-8"))
    rows = read_csv(root / "formal_b2/figure_data/representative_case_rows.csv")
    weak_case_id = representatives["primary_weak_C_figure"]["case_id"]
    row = next(item for item in rows if item["case_id"] == weak_case_id)
    image = Image.new("RGB", (1600, 820), BG)
    draw = ImageDraw.Draw(image)
    draw.text((45, 24), "Frozen weak-C representative: controller, exact oracle, and plug-in", font=font(34, True), fill=INK)
    draw.text((45, 70), f"{weak_case_id} · lowest numeric seed among eligible cases after all {summary['formal_case_count']} results were sealed", font=font(18), fill=MUTED)
    labels = {
        "FINE": ("FINE", BLUE),
        "SECTOR_SAFE": ("SECTOR", GREEN),
        "SUPPORT_AMBIGUOUS": ("SUPPORT AMBIG.", ORANGE),
        "ABSENT_ABOVE_BETA_MIN": ("ABSENT", "#7B8794"),
        "ABSTAIN": ("ABSTAIN", RED),
    }
    methods = [("Controller", "stage_a_controller"), ("Exact oracle", "oracle"), ("Plug-in", "plugin")]
    left, top, cell_w, cell_h = 290, 160, 285, 155
    for j, region in enumerate("ABCD"):
        draw_text_center(draw, (left + j * cell_w + cell_w / 2, top - 42), f"Region {region}", font(23, True), INK)
    for i, (method, prefix) in enumerate(methods):
        draw.text((55, top + i * cell_h + 54), method, font=font(24, True), fill=INK)
        for j, region in enumerate("ABCD"):
            raw = row[f"{prefix}_{region}"]
            label, color = labels[raw]
            box = (left + j * cell_w + 8, top + i * cell_h + 8, left + (j + 1) * cell_w - 8, top + (i + 1) * cell_h - 8)
            draw.rounded_rectangle(box, radius=18, fill=color, outline="#FFFFFF", width=3)
            draw_text_center(draw, ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), label, font(20, True), "#FFFFFF")
    draw.text((45, 670), f"Application-specific local map on a frozen {summary['application']['candidate_explanation_count']}-explanation finite bank.", font=font(19), fill=INK)
    draw.text((45, 708), f"{empty_profile['case_id']} is a native empty profile and is not displayed as a map.", font=font(18), fill=INK)
    draw.text((45, 748), "The plug-in comparison is scoped to this fixed synthetic application; no general solver-inferiority claim is made.", font=font(18), fill=MUTED)
    save_png_pdf(image, root / "paper/figures/formal_b2_weak_c_map.png", root / "paper/figures/formal_b2_weak_c_map.pdf", "Formal B2 frozen weak-C representative")
    return {
        "representative_case_id": {"canonical_field": "formal_b2/representative_examples.json::$.primary_weak_C_figure.case_id", "value": weak_case_id},
        "formal_case_count": {"canonical_field": "formal_b2/canonical_merged_summary.json::$.formal_case_count", "value": summary["formal_case_count"]},
        "candidate_explanation_count": {"canonical_field": "formal_b2/canonical_merged_summary.json::$.application.candidate_explanation_count", "value": summary["application"]["candidate_explanation_count"]},
        "empty_profile_case_id": {"canonical_field": "formal_b2/empty_profile_disclosure.json::$.case_id", "value": empty_profile["case_id"]},
    }


def generate_f5c(root: Path) -> dict:
    rows = read_csv(root / "formal_b2/figure_data/plugin_false_precision.csv")
    image = Image.new("RGB", (1300, 820), BG)
    draw = ImageDraw.Draw(image)
    draw.text((45, 24), "Plug-in false precision in eligible weak-C cases", font=font(34, True), fill=INK)
    draw.text((45, 70), "One frozen synthetic finite-bank application", font=font(20), fill=MUTED)
    labels = {"plugin_B_false_FINE": "B: false FINE", "plugin_C_false_certainty": "C: false certainty"}
    colors = [ORANGE, PURPLE]
    baseline, max_h = 650, 470
    for idx, row in enumerate(rows):
        rate = float(row["rate"])
        left = 230 + idx * 500
        right = left + 320
        top = baseline - rate * max_h
        draw.rounded_rectangle((left, top, right, baseline), radius=18, fill=colors[idx])
        draw_text_center(draw, ((left + right) / 2, top - 42), f"{row['numerator']}/{row['denominator']}", font(30, True), colors[idx])
        draw_text_center(draw, ((left + right) / 2, baseline + 48), labels[row["metric"]], font(23, True), INK)
    draw.line((120, baseline, 1180, baseline), fill=INK, width=3)
    draw.text((45, 755), "Eligible-case comparison only; no general inferiority claim for plug-in solvers.", font=font(19), fill=INK)
    save_png_pdf(image, root / "paper/figures/formal_b2_plugin_false_precision.png", root / "paper/figures/formal_b2_plugin_false_precision.pdf", "Formal B2 plug-in false precision")
    return {
        row["metric"]: {
            "canonical_field": f"formal_b2/figure_data/plugin_false_precision.csv::{row['metric']}",
            "value": f"{row['numerator']}/{row['denominator']}",
        }
        for row in rows
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.export_root.resolve()
    receipt = {
        "schema_version": "M0B_FIGURE_GENERATION_RECEIPT_V1",
        "generator_script": "paper/generators/generate_paper_figures.py",
        "displayed_canonical_fields": {
            "F2": generate_f2(root),
            "F4": generate_f4(root),
            "F5a": generate_f5a(root),
            "F5b": generate_f5b(root),
            "F5c": generate_f5c(root),
        },
    }
    receipt_path = root / "paper/figure_generation_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
