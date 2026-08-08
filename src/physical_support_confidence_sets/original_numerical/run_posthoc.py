"""Post-hoc robustness audit that cannot alter the frozen R0 status."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import NullFormatter

from .exact_mixture import estimate_pair_batches, gauss_hermite_pair_diagnostics
from .run_pilot import build_mixture, log_slope, read_json, run_stress, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--output", type=Path, default=Path("results/posthoc"))
    arguments = parser.parse_args()
    config = read_json(arguments.config)
    output = arguments.output
    output.mkdir(parents=True, exist_ok=True)

    geometry = config["geometry"]
    s = 0.082
    h_grid = np.asarray([0.10, 0.15, 0.20, 0.25, 0.35, 0.45])
    rows = []
    for h in h_grid:
        actual_angle = h * geometry["generator_scale"]
        first = build_mixture(config, s, 0.0)
        second = build_mixture(config, s, actual_angle)
        batches = estimate_pair_batches(first, second, 32, 8192, 2026072221)
        for item in batches:
            rows.append({"s": s, "h": h, **item})
    batch_frame = pd.DataFrame(rows)
    summary = batch_frame.groupby("h", as_index=False).agg(
        jeffreys=("jeffreys", "mean"),
        affinity_deficit=("affinity_deficit", "mean"),
    )
    fit = log_slope(summary["h"], summary["jeffreys"])
    scaled = summary["jeffreys"] / summary["h"] ** 2
    h_metrics = {
        **fit,
        "scaled_max_min_ratio": float(scaled.max() / scaled.min()),
    }
    h_pass = (
        1.85 <= h_metrics["slope"] <= 2.10
        and h_metrics["r_squared"] >= 0.995
        and h_metrics["scaled_max_min_ratio"] <= 1.20
    )
    batch_frame.to_csv(output / "h_scaling_batches.csv", index=False)
    summary.to_csv(output / "h_scaling_summary.csv", index=False)

    stress_frame, stress_metrics = run_stress(config, output)
    quadrature_rows = []
    actual_angle = geometry["orientation_path_parameter"] * geometry["generator_scale"]
    for collision_scale in config["confirmatory"]["s_grid"]:
        first = build_mixture(config, collision_scale, 0.0)
        second = build_mixture(config, collision_scale, actual_angle)
        item = gauss_hermite_pair_diagnostics(first, second, 14)
        item["s"] = collision_scale
        quadrature_rows.append(item)
    quadrature = pd.DataFrame(quadrature_rows).sort_values("s")
    quadrature.to_csv(output / "gauss_hermite_all_s_order14.csv", index=False)
    quadrature_fit = log_slope(quadrature["s"], quadrature["jeffreys"])
    quadrature_ratio = float(
        (quadrature["jeffreys"] / quadrature["s"] ** 6).max()
        / (quadrature["jeffreys"] / quadrature["s"] ** 6).min()
    )
    status = (
        "R0_HOLD_BUT_GEOMETRY_ROBUST"
        if h_pass and stress_metrics["pass"]
        else "HOLD_NUMERICAL_EVIDENCE"
    )
    payload = {
        "status": status,
        "r0_status_unchanged": "HOLD_NUMERICAL_EVIDENCE",
        "h_scaling": {**h_metrics, "pass": h_pass},
        "stress": stress_metrics,
        "all_s_order14_quadrature": {
            "slope": quadrature_fit["slope"],
            "r_squared": quadrature_fit["r_squared"],
            "scaled_max_min_ratio": quadrature_ratio,
            "diagnostic_only": True
        },
    }
    write_json(output / "posthoc_adjudication.json", payload)

    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    figure_directory = output / "figures"
    figure_directory.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9), constrained_layout=True)
    reference = summary["jeffreys"].iloc[2] * (summary["h"] / summary["h"].iloc[2]) ** 2
    axes[0].plot(summary["h"], summary["jeffreys"], "o-", label="Exact-mixture MC")
    axes[0].plot(summary["h"], reference, "--", label=r"Reference $h^2$")
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Path parameter $h$")
    axes[0].set_ylabel("Jeffreys divergence")
    axes[0].set_title("(a) Quadratic path scaling")
    axes[0].legend(frameon=False)
    axes[0].set_xticks([0.1, 0.2, 0.4])
    axes[0].set_xticklabels(["0.1", "0.2", "0.4"])
    axes[0].xaxis.set_minor_formatter(NullFormatter())
    pivot = stress_frame.pivot(index="nu", columns="p", values="slope").sort_index(ascending=False)
    image = axes[1].imshow(pivot.to_numpy(), vmin=5.4, vmax=6.6, cmap="RdYlBu_r", aspect="auto")
    axes[1].set_xticks(range(len(pivot.columns)), [f"{value:g}" for value in pivot.columns])
    axes[1].set_yticks(range(len(pivot.index)), [f"{value:g}" for value in pivot.index])
    axes[1].set_xlabel("Activation probability p")
    axes[1].set_ylabel("Noise variance nu")
    axes[1].set_title("(b) Stress-grid s exponent")
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            axes[1].text(j, i, f"{pivot.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=axes[1], label="Fitted exponent")
    for suffix in ("pdf", "png"):
        fig.savefig(figure_directory / f"posthoc_robustness.{suffix}", bbox_inches="tight", dpi=300)
    plt.close(fig)

    report = [
        "# Post-hoc robustness diagnostic R0.1",
        "",
        f"**Interpretation: `{status}`**",
        "",
        "The frozen R0 status remains `HOLD_NUMERICAL_EVIDENCE`; this report does not change it.",
        "",
        f"- h-scaling slope: `{h_metrics['slope']:.4f}` (R-squared `{h_metrics['r_squared']:.6f}`).",
        f"- max/min of J/h^2: `{h_metrics['scaled_max_min_ratio']:.4f}`.",
        f"- stress-grid s slopes: `{stress_metrics['minimum_slope']:.4f}` to `{stress_metrics['maximum_slope']:.4f}`.",
        f"- failed stress cells: `{stress_metrics['failed_cells']}`.",
        f"- all-s order-14 quadrature exponent (descriptive): `{quadrature_fit['slope']:.4f}`.",
        f"- all-s quadrature max/min of J/s^6: `{quadrature_ratio:.4f}`.",
        "",
        "This is a robustness interpretation only. It cannot be reported as a preregistered confirmatory pass.",
        "",
    ]
    (output / "POSTHOC_DIAGNOSTIC_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if status == "R0_HOLD_BUT_GEOMETRY_ROBUST" else 2


if __name__ == "__main__":
    raise SystemExit(main())
