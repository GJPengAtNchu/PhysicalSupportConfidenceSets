#!/usr/bin/env python3
"""Reproduce paper tables from immutable canonical JSON/CSV exports."""

from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterable


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_rows(path: Path, fieldnames: tuple[str, ...], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _ratio(metric: dict) -> str:
    return f"{metric['numerator']}/{metric['denominator']}"


def _query_fraction(value: float) -> str:
    ratio = Fraction(value).limit_denominator(10_000)
    return f"{ratio.numerator}/{ratio.denominator} ({value:.4f})"


def _b11_rows(root: Path) -> list[dict[str, str]]:
    summary = json.loads((root / "b11_global/canonical_summary.json").read_text(encoding="utf-8"))
    safety = json.loads((root / "b11_global/safety_metrics.json").read_text(encoding="utf-8"))
    half, three_quarters = summary["budget_0_50"], summary["budget_0_75"]

    def outputs(record: dict) -> str:
        order = ("ABSTAIN", "AMBIGUOUS", "FINE", "SECTOR_SAFE")
        return "; ".join(
            f"{record['outputs'][label]} {label}"
            for label in order
            if record["outputs"].get(label)
        )

    rows = [
        ("Output counts", outputs(half), outputs(three_quarters), "54 traces at each displayed budget"),
        ("Non-abstain yield", _ratio(half["nonabstain_yield"]), _ratio(three_quarters["nonabstain_yield"]), "all sealed traces"),
        ("AMBIGUOUS recall", _ratio(half["ambiguous_recall"]), _ratio(three_quarters["ambiguous_recall"]), "oracle-AMBIGUOUS traces"),
        ("FINE recall", _ratio(half["fine_recall"]), _ratio(three_quarters["fine_recall"]), "oracle-FINE traces"),
        ("Safe nonambiguous", _ratio(half["safe_nonambiguous_rate"]), _ratio(three_quarters["safe_nonambiguous_rate"]), "oracle-nonambiguous traces"),
        ("Median query fraction", _query_fraction(half["median_logical_query_fraction"]), _query_fraction(three_quarters["median_logical_query_fraction"]), "exact logical-query fraction with four-decimal display"),
        ("Worst query fraction", _query_fraction(half["worst_logical_query_fraction"]), _query_fraction(three_quarters["worst_logical_query_fraction"]), "exact logical-query fraction with four-decimal display"),
        ("Structural unsafe decisions", f"{safety['structural_unsafe_count']} (global audit)", f"{safety['structural_unsafe_count']} (global audit)", "0 across 324 audited budget results; not budget-specific"),
        ("Trace-prefix bound violations", f"{safety['bound_violation_count']} (global audit; denominator null)", f"{safety['bound_violation_count']} (global audit; denominator null)", "sealed B1.1 source defines no canonical denominator; never report 0/54"),
    ]
    return [dict(zip(("metric", "budget_0_50", "budget_0_75", "scope_note"), row)) for row in rows]


def _formal_rows(root: Path) -> list[dict[str, str]]:
    summary = json.loads((root / "formal_b2/canonical_merged_summary.json").read_text(encoding="utf-8"))
    empty = json.loads((root / "formal_b2/empty_profile_disclosure.json").read_text(encoding="utf-8"))
    secondary = json.loads((root / "formal_b2/secondary_prefix_metrics.json").read_text(encoding="utf-8"))
    app, safety, coverage, utility = summary["application"], summary["safety"], summary["coverage"], summary["utility"]
    plugin = summary["plugin_false_precision"]
    rows = [
        ("Design", "Regions / response atoms", f"{len(app['regions'])} / {app['target_response_atom_count']}"),
        ("Design", "Dictionary states / explanations", f"{app['dictionary_state_count']} / {app['candidate_explanation_count']}"),
        ("Design", "Calibration / deployment sizes", f"{app['calibration_size_N']} / {app['deployment_replicates_T']}"),
        ("Cases", "Formal datasets", str(summary["formal_case_count"])),
        ("Cases", "Completed exact oracles", f"{summary['completed_exact_oracle_count']}/{summary['formal_case_count']}"),
        ("Cases", "Administrative empty profile", f"{summary['administrative_empty_profile_count']}/{summary['formal_case_count']}"),
        ("Safety", "Unsafe outputs", _ratio(safety["zero_unsafe_outputs"])),
        ("Safety", "Possible-set violations", _ratio(safety["zero_possible_set_violations"])),
        ("Safety", "Completed-prefix bound violations", _ratio(safety["zero_bound_violations"])),
        ("Safety", "False D absence in controls", _ratio(safety["control_false_D_absence"])),
        ("Coverage", "Main oracle coverage", _ratio(coverage["main_oracle_coverage"])),
        ("Coverage", "Control oracle coverage", _ratio(coverage["control_oracle_coverage"])),
        ("Utility", "Controller A FINE recall", _ratio(utility["controller_A_FINE_recall"])),
        ("Utility", "Controller B SECTOR recall", _ratio(utility["controller_B_SECTOR_recall"])),
        ("Utility", "Controller C ambiguity recall", _ratio(utility["controller_C_ambiguity_recall"])),
        ("Utility", "Controller D absence recall", _ratio(utility["controller_D_absence_recall"])),
        ("Plug-in", "B false FINE", _ratio(plugin["plugin_B_false_FINE"])),
        ("Plug-in", "C false certainty", _ratio(plugin["plugin_C_false_certainty"])),
        ("Cost", "Median primary queries", _ratio(summary["cost"]["median_query_fraction"])),
        ("Descriptive prefix", "108-query prefix", "descriptive only; no secondary controller run" if not secondary["separate_controller_run"] else "separate controller run"),
        ("Empty profile", "P05 native status", empty["native_status"]),
        ("Empty profile", "P05 reported physical map", "null" if empty["reported_physical_map"] is None else str(empty["reported_physical_map"])),
        ("Empty profile", "Utility / bound / Stage-A cost", "excluded / excluded / 162 retained"),
    ]
    return [dict(zip(("block", "metric", "result"), row)) for row in rows]


def _original_rows(root: Path) -> list[dict[str, str]]:
    summary = json.loads((root / "original_numerical/canonical_summary.json").read_text(encoding="utf-8"))
    rows = [
        ("Frozen status", summary["status"], "illustration only"),
        ("Jeffreys s-exponent", f"{summary['scaling']['jeffreys']['slope']:.10f}", "frozen illustration"),
        ("Median product-affinity spread", f"{summary['gate_collapse']['median_vertical_spread']:.10f}", "failed <=0.015 criterion"),
        ("Post-hoc h-exponent", f"{summary['posthoc_h_slope']:.4f}", "post-hoc only"),
    ]
    return [dict(zip(("metric", "value", "scope"), row)) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("build/table_reproduction"))
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    canonical = repository / "artifacts" / "canonical_paper_export"
    output = (repository / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir.resolve()
    build_root = (repository / "build").resolve()
    try:
        output.relative_to(build_root)
    except ValueError as error:
        raise ValueError("--output-dir must resolve below the repository build directory") from error
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    products = {
        "b11_global_validation.csv": (("metric", "budget_0_50", "budget_0_75", "scope_note"), _b11_rows(canonical)),
        "formal_b2_application_gates.csv": (("block", "metric", "result"), _formal_rows(canonical)),
        "original_numerical_disclosure.csv": (("metric", "value", "scope"), _original_rows(canonical)),
    }
    for name, (fields, rows) in products.items():
        destination = output / name
        _write_rows(destination, fields, rows)
        frozen = canonical / "paper" / "tables" / name
        if _read_rows(destination) != _read_rows(frozen):
            raise AssertionError(f"regenerated table differs from canonical values: {name}")

    # T1 and the two TeX layouts are frozen formatting exports. Reproduction
    # copies those bytes after the numeric CSVs above have been re-derived.
    for name in (
        "theory_to_output_map.csv",
        "b11_global_validation.tex",
        "formal_b2_application_gates.tex",
    ):
        shutil.copyfile(canonical / "paper" / "tables" / name, output / name)

    outputs = sorted(path for path in output.iterdir() if path.is_file())
    receipt = {
        "schema_version": "PUBLICATION_TABLE_REPRODUCTION_V1",
        "source": "artifacts/canonical_paper_export",
        "scientific_values_changed": False,
        "outputs": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in outputs
        },
    }
    receipt_path = output / "table_reproduction_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Reproduced {len(outputs)} table files in {output}")
    print(f"Canonical values: verified ({receipt_path})")


if __name__ == "__main__":
    main()

