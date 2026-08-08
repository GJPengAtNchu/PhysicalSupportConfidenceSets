"""Run, adjudicate, and report the frozen three-gate simulation pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from matplotlib.ticker import ScalarFormatter
from scipy import stats

from .exact_mixture import (
    GaussianMixture,
    estimate_pair_batches,
    gauss_hermite_pair_diagnostics,
    product_affinity_deficit,
)
from .geometry import (
    parent_pair,
    profiled_task_residual,
    projective_matching,
    sparse_mean,
    balanced_dictionary,
    wrong_support_pair,
)


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def t_summary(values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, dtype=float)
    mean = float(np.mean(values))
    standard_error = float(stats.sem(values))
    critical = float(stats.t.ppf(0.975, len(values) - 1))
    half_width = critical * standard_error
    return {
        "mean": mean,
        "standard_error": standard_error,
        "ci_lower": mean - half_width,
        "ci_upper": mean + half_width,
        "relative_ci_half_width": half_width / mean,
    }


def log_slope(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    result = stats.linregress(np.log(np.asarray(x)), np.log(np.asarray(y)))
    return {
        "slope": float(result.slope),
        "intercept": float(result.intercept),
        "r_squared": float(result.rvalue**2),
        "standard_error": float(result.stderr),
    }


def paired_bootstrap_slopes(
    batch_frame: pd.DataFrame,
    metric: str,
    repetitions: int,
    seed: int,
) -> tuple[float, float]:
    pivot = batch_frame.pivot(index="batch", columns="s", values=metric).sort_index(
        axis=1
    )
    x = np.log(pivot.columns.to_numpy(dtype=float))
    values = pivot.to_numpy()
    rng = np.random.default_rng(seed)
    slopes = np.empty(repetitions)
    centered_x = x - x.mean()
    denominator = float(centered_x @ centered_x)
    for repetition in range(repetitions):
        indices = rng.integers(0, len(values), len(values))
        means = values[indices].mean(axis=0)
        slopes[repetition] = float(centered_x @ np.log(means) / denominator)
    return tuple(np.quantile(slopes, [0.025, 0.975]).tolist())


def build_mixture(config: dict, s: float, actual_angle: float) -> GaussianMixture:
    training = config["training"]
    geometry = config["geometry"]
    return GaussianMixture.bernoulli_gaussian(
        s=s,
        angle=actual_angle,
        p=training["p"],
        nu=training["nu"],
        coefficient_variance=training["coefficient_variance"],
        lambda_star=geometry["lambda_star"],
    )


def run_confirmatory(config: dict, output: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    confirmatory = config["confirmatory"]
    geometry = config["geometry"]
    actual_angle = (
        geometry["orientation_path_parameter"] * geometry["generator_scale"]
    )
    rows = []
    for s in confirmatory["s_grid"]:
        first = build_mixture(config, s, 0.0)
        second = build_mixture(config, s, actual_angle)
        estimates = estimate_pair_batches(
            first,
            second,
            batches=confirmatory["mc_batches"],
            batch_size=confirmatory["mc_batch_size"],
            # The identical seed for every s creates paired common random numbers.
            seed=confirmatory["seed"],
        )
        for estimate in estimates:
            estimate.update({"s": s, "actual_angle": actual_angle})
            rows.append(estimate)
    batches = pd.DataFrame(rows)
    summaries = []
    for s, group in batches.groupby("s", sort=True):
        row = {"s": float(s)}
        for metric in ("jeffreys", "affinity_deficit"):
            summary = t_summary(group[metric].to_numpy())
            for key, value in summary.items():
                row[f"{metric}_{key}"] = value
        row["jeffreys_over_s6"] = row["jeffreys_mean"] / s**6
        row["affinity_deficit_over_s6"] = row["affinity_deficit_mean"] / s**6
        row["local_identity_ratio"] = row["jeffreys_mean"] / (
            8.0 * row["affinity_deficit_mean"]
        )
        summaries.append(row)
    summary_frame = pd.DataFrame(summaries).sort_values("s")

    metrics = {}
    for metric in ("jeffreys", "affinity_deficit"):
        fit = log_slope(summary_frame["s"], summary_frame[f"{metric}_mean"])
        fit["bootstrap_ci_lower"], fit["bootstrap_ci_upper"] = paired_bootstrap_slopes(
            batches,
            metric,
            confirmatory["bootstrap_repetitions"],
            confirmatory["bootstrap_seed"] + (0 if metric == "jeffreys" else 1),
        )
        scaled = summary_frame[f"{metric}_over_s6"]
        fit["scaled_max_min_ratio"] = float(scaled.max() / scaled.min())
        metrics[metric] = fit

    midpoint = confirmatory["mc_batches"] // 2
    first_half = batches[batches["batch"] < midpoint]
    second_half = batches[batches["batch"] >= midpoint]
    metrics["half_sample"] = {}
    for metric in ("jeffreys", "affinity_deficit"):
        first_means = first_half.groupby("s")[metric].mean()
        second_means = second_half.groupby("s")[metric].mean()
        first_fit = log_slope(first_means.index.to_numpy(), first_means.to_numpy())
        second_fit = log_slope(second_means.index.to_numpy(), second_means.to_numpy())
        metrics["half_sample"][metric] = {
            "first_slope": first_fit["slope"],
            "second_slope": second_fit["slope"],
            "absolute_difference": abs(first_fit["slope"] - second_fit["slope"]),
        }

    batches.to_csv(output / "confirmatory_batches.csv", index=False)
    summary_frame.to_csv(output / "confirmatory_summary.csv", index=False)
    return batches, summary_frame, metrics


def run_gauss_hermite(config: dict, summary: pd.DataFrame, output: Path) -> tuple[pd.DataFrame, dict]:
    confirmatory = config["confirmatory"]
    geometry = config["geometry"]
    actual_angle = (
        geometry["orientation_path_parameter"] * geometry["generator_scale"]
    )
    rows = []
    for s in confirmatory["gauss_hermite_s_grid"]:
        first = build_mixture(config, s, 0.0)
        second = build_mixture(config, s, actual_angle)
        for order in confirmatory["gauss_hermite_orders"]:
            values = gauss_hermite_pair_diagnostics(first, second, order)
            values["s"] = s
            rows.append(values)
    frame = pd.DataFrame(rows).sort_values(["s", "order"])
    checks = []
    threshold = config["criteria"]["gauss_hermite_relative_difference_maximum"]
    highest_order = max(confirmatory["gauss_hermite_orders"])
    for s in confirmatory["gauss_hermite_s_grid"]:
        mc = summary.loc[np.isclose(summary["s"], s)].iloc[0]
        group = frame[frame["s"] == s].set_index("order")
        for metric in ("jeffreys", "affinity_deficit"):
            low = float(group.loc[min(group.index), metric])
            high = float(group.loc[highest_order, metric])
            mc_mean = float(mc[f"{metric}_mean"])
            mc_se = float(mc[f"{metric}_standard_error"])
            order_difference = abs(high - low) / high
            mc_difference = abs(high - mc_mean) / high
            allowed_mc = max(threshold, 2.0 * mc_se / mc_mean)
            checks.append(
                {
                    "s": s,
                    "metric": metric,
                    "order_relative_difference": order_difference,
                    "mc_relative_difference": mc_difference,
                    "mc_allowed_relative_difference": allowed_mc,
                    "pass": bool(
                        order_difference <= threshold and mc_difference <= allowed_mc
                    ),
                }
            )
    frame.to_csv(output / "gauss_hermite_crosscheck.csv", index=False)
    pd.DataFrame(checks).to_csv(output / "gauss_hermite_checks.csv", index=False)
    return frame, {"checks": checks, "pass": all(item["pass"] for item in checks)}


def run_gate_curves(config: dict, summary: pd.DataFrame, output: Path) -> tuple[pd.DataFrame, dict]:
    geometry = config["geometry"]
    test = config["test"]
    budgets = np.asarray(config["confirmatory"]["information_budget_grid"])
    rows = []
    for record in summary.itertuples(index=False):
        s = float(record.s)
        fine, anchor = parent_pair(
            s,
            beta=test["beta"],
            support=tuple(geometry["support_zero_based"]),
            lambda_star=geometry["lambda_star"],
        )
        support_zero, support_one = wrong_support_pair(
            s,
            beta=test["beta"],
            support=tuple(geometry["support_zero_based"]),
            alternative=tuple(geometry["alternative_support_zero_based"]),
            lambda_star=geometry["lambda_star"],
        )
        parent_constant = np.linalg.norm(fine - anchor) ** 2 / (
            geometry["r"] ** 2 * test["beta"] ** 2
        )
        support_constant = np.linalg.norm(support_zero - support_one) ** 2 / (
            test["beta"] ** 2 * s**2
        )
        for budget in budgets:
            parent_error = stats.norm.cdf(-math.sqrt(budget * parent_constant) / 2.0)
            support_error = stats.norm.cdf(-math.sqrt(budget * support_constant) / 2.0)
            parent_affinity = math.exp(-budget * parent_constant / 8.0)
            support_affinity = math.exp(-budget * support_constant / 8.0)
            sample_size = max(1, int(round(float(budget / s**6))))
            dictionary_deficit = float(
                product_affinity_deficit(record.affinity_deficit_mean, sample_size)
            )
            dictionary_affinity = 1.0 - dictionary_deficit
            lower_error = (1.0 - math.sqrt(max(0.0, 1.0 - dictionary_affinity**2))) / 2.0
            upper_error = dictionary_affinity / 2.0
            rows.extend(
                [
                    {
                        "gate": "parent",
                        "s": s,
                        "budget": budget,
                        "sample_size": budget
                        * test["sigma"] ** 2
                        / (geometry["r"] ** 2 * test["beta"] ** 2),
                        "primary": parent_error,
                        "affinity": parent_affinity,
                        "lower": parent_error,
                        "upper": parent_error,
                    },
                    {
                        "gate": "support",
                        "s": s,
                        "budget": budget,
                        "sample_size": budget
                        * test["sigma"] ** 2
                        / (test["beta"] ** 2 * s**2),
                        "primary": support_error,
                        "affinity": support_affinity,
                        "lower": support_error,
                        "upper": support_error,
                    },
                    {
                        "gate": "dictionary",
                        "s": s,
                        "budget": budget,
                        "sample_size": sample_size,
                        "primary": dictionary_affinity,
                        "affinity": dictionary_affinity,
                        "lower": lower_error,
                        "upper": upper_error,
                    },
                ]
            )
    frame = pd.DataFrame(rows)
    dictionary = frame[frame["gate"] == "dictionary"]
    spreads = dictionary.groupby("budget")["primary"].agg(
        spread=lambda values: values.max() - values.min(), mean="mean"
    )
    transition = spreads[(spreads["mean"] >= 0.1) & (spreads["mean"] <= 0.9)]
    if transition.empty:
        transition = spreads
    metrics = {
        "maximum_vertical_spread": float(transition["spread"].max()),
        "median_vertical_spread": float(transition["spread"].median()),
        "transition_budgets": transition.index.to_list(),
    }
    frame.to_csv(output / "gate_curves.csv", index=False)
    spreads.reset_index().to_csv(output / "dictionary_collapse.csv", index=False)
    return frame, metrics


def run_task_controls(config: dict, output: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    geometry = config["geometry"]
    test = config["test"]
    phi_spec = config["confirmatory"]["task_phi_grid"]
    phis = np.linspace(phi_spec["minimum"], phi_spec["maximum"], phi_spec["count"])
    rows = []
    matching_rows = []
    for s in config["confirmatory"]["s_grid"]:
        for phi in phis:
            matching, identity_gap, next_best_gap = projective_matching(
                s, phi, geometry["lambda_star"]
            )
            matching_rows.append(
                {
                    "s": s,
                    "phi": phi,
                    "matching": "-".join(map(str, matching.tolist())),
                    "identity_gap": identity_gap,
                    "next_best_gap": next_best_gap,
                    "same_label": bool(np.array_equal(matching, np.arange(4))),
                }
            )
            for contrast in test["contrasts"]:
                numerical, analytic = profiled_task_residual(
                    s,
                    phi,
                    test["mean_coefficient"],
                    contrast,
                    support=tuple(geometry["support_zero_based"]),
                    lambda_star=geometry["lambda_star"],
                )
                relative = (
                    abs(numerical - analytic) / analytic if analytic > 1e-14 else np.nan
                )
                rows.append(
                    {
                        "s": s,
                        "phi": phi,
                        "contrast": contrast,
                        "numerical_residual": numerical,
                        "analytic_residual": analytic,
                        "absolute_error": abs(numerical - analytic),
                        "relative_error": relative,
                    }
                )
    frame = pd.DataFrame(rows)
    matching_frame = pd.DataFrame(matching_rows)
    equal = frame[frame["contrast"] == 0.0]
    nonzero = frame[(frame["contrast"] != 0.0) & frame["relative_error"].notna()]
    metrics = {
        "maximum_equal_coefficient_residual": float(equal["numerical_residual"].max()),
        "maximum_contrast_formula_relative_error": float(nonzero["relative_error"].max()),
        "same_label_matching_everywhere": bool(matching_frame["same_label"].all()),
        "minimum_next_best_matching_gap": float(matching_frame["next_best_gap"].min()),
    }
    frame.to_csv(output / "task_controls.csv", index=False)
    matching_frame.to_csv(output / "projective_matching.csv", index=False)
    return frame, matching_frame, metrics


def adjudicate(
    config: dict,
    summary: pd.DataFrame,
    scaling: dict,
    gates: dict,
    task: dict,
    gauss_hermite: dict,
) -> tuple[str, list[dict]]:
    criteria = config["criteria"]
    checks = []

    def add(name: str, value, relation: str, threshold, passed: bool) -> None:
        checks.append(
            {
                "check": name,
                "value": value,
                "relation": relation,
                "threshold": threshold,
                "pass": bool(passed),
            }
        )

    for metric, label in (("jeffreys", "Jeffreys"), ("affinity_deficit", "Affinity deficit")):
        lower = criteria[
            "jeffreys_slope_minimum" if metric == "jeffreys" else "hellinger_slope_minimum"
        ]
        upper = criteria[
            "jeffreys_slope_maximum" if metric == "jeffreys" else "hellinger_slope_maximum"
        ]
        r2_threshold = criteria[
            "jeffreys_r_squared_minimum"
            if metric == "jeffreys"
            else "hellinger_r_squared_minimum"
        ]
        ratio_threshold = criteria[
            "scaled_jeffreys_ratio_maximum"
            if metric == "jeffreys"
            else "scaled_hellinger_ratio_maximum"
        ]
        add(
            f"{label} log-log slope",
            scaling[metric]["slope"],
            "inside",
            [lower, upper],
            lower <= scaling[metric]["slope"] <= upper,
        )
        add(
            f"{label} R-squared",
            scaling[metric]["r_squared"],
            ">=",
            r2_threshold,
            scaling[metric]["r_squared"] >= r2_threshold,
        )
        add(
            f"{label}/s^6 max-min ratio",
            scaling[metric]["scaled_max_min_ratio"],
            "<=",
            ratio_threshold,
            scaling[metric]["scaled_max_min_ratio"] <= ratio_threshold,
        )
        max_relative_ci = float(summary[f"{metric}_relative_ci_half_width"].max())
        add(
            f"{label} maximum relative CI half-width",
            max_relative_ci,
            "<=",
            criteria["relative_ci_half_width_maximum"],
            max_relative_ci <= criteria["relative_ci_half_width_maximum"],
        )
        half_difference = scaling["half_sample"][metric]["absolute_difference"]
        add(
            f"{label} half-sample slope difference",
            half_difference,
            "<=",
            criteria["half_sample_slope_difference_maximum"],
            half_difference <= criteria["half_sample_slope_difference_maximum"],
        )

    identity_min = float(summary["local_identity_ratio"].min())
    identity_max = float(summary["local_identity_ratio"].max())
    add(
        "Jeffreys / (8 affinity deficit)",
        [identity_min, identity_max],
        "inside",
        [criteria["local_identity_ratio_minimum"], criteria["local_identity_ratio_maximum"]],
        identity_min >= criteria["local_identity_ratio_minimum"]
        and identity_max <= criteria["local_identity_ratio_maximum"],
    )
    add(
        "Dictionary product-affinity maximum spread",
        gates["maximum_vertical_spread"],
        "<=",
        criteria["dictionary_collapse_maximum_spread"],
        gates["maximum_vertical_spread"] <= criteria["dictionary_collapse_maximum_spread"],
    )
    add(
        "Dictionary product-affinity median spread",
        gates["median_vertical_spread"],
        "<=",
        criteria["dictionary_collapse_median_spread"],
        gates["median_vertical_spread"] <= criteria["dictionary_collapse_median_spread"],
    )
    add(
        "Equal-coefficient test residual",
        task["maximum_equal_coefficient_residual"],
        "<=",
        criteria["equal_coefficient_residual_maximum"],
        task["maximum_equal_coefficient_residual"]
        <= criteria["equal_coefficient_residual_maximum"],
    )
    add(
        "Two-atom contrast formula relative error",
        task["maximum_contrast_formula_relative_error"],
        "<=",
        criteria["contrast_formula_relative_error_maximum"],
        task["maximum_contrast_formula_relative_error"]
        <= criteria["contrast_formula_relative_error_maximum"],
    )
    add(
        "Same-label projective matching",
        task["same_label_matching_everywhere"],
        "is",
        True,
        task["same_label_matching_everywhere"],
    )
    add(
        "Gauss-Hermite cross-check",
        gauss_hermite["pass"],
        "is",
        True,
        gauss_hermite["pass"],
    )
    if all(item["pass"] for item in checks):
        status = "GO_FOR_MANUSCRIPT_INTEGRATION"
    else:
        core_names = {"Jeffreys log-log slope", "Affinity deficit log-log slope", "Equal-coefficient test residual"}
        core_failed = any(not item["pass"] and item["check"] in core_names for item in checks)
        status = "NO_GO_THEOREM_NATIVE_SIMULATION" if core_failed else "HOLD_NUMERICAL_EVIDENCE"
    return status, checks


def run_stress(config: dict, output: Path) -> tuple[pd.DataFrame, dict]:
    stress = config["stress"]
    geometry = config["geometry"]
    actual_angle = geometry["orientation_path_parameter"] * geometry["generator_scale"]
    rows = []
    combination = 0
    for p in stress["p_grid"]:
        for nu in stress["nu_grid"]:
            summaries = []
            for s in stress["s_grid"]:
                local = json.loads(json.dumps(config))
                local["training"]["p"] = p
                local["training"]["nu"] = nu
                first = build_mixture(local, s, 0.0)
                second = build_mixture(local, s, actual_angle)
                batches = estimate_pair_batches(
                    first,
                    second,
                    stress["mc_batches"],
                    stress["mc_batch_size"],
                    stress["seed"] + combination,
                )
                summaries.append((s, float(np.mean([item["jeffreys"] for item in batches]))))
            x = np.asarray([item[0] for item in summaries])
            y = np.asarray([item[1] for item in summaries])
            fit = log_slope(x, y)
            rows.append(
                {
                    "p": p,
                    "nu": nu,
                    "slope": fit["slope"],
                    "r_squared": fit["r_squared"],
                    "scaled_max_min_ratio": float(np.max(y / x**6) / np.min(y / x**6)),
                }
            )
            combination += 1
    frame = pd.DataFrame(rows)
    lower = config["criteria"]["stress_slope_minimum"]
    upper = config["criteria"]["stress_slope_maximum"]
    frame["pass"] = frame["slope"].between(lower, upper)
    frame.to_csv(output / "stress_summary.csv", index=False)
    return frame, {
        "pass": bool(frame["pass"].all()),
        "minimum_slope": float(frame["slope"].min()),
        "maximum_slope": float(frame["slope"].max()),
        "failed_cells": int((~frame["pass"]).sum()),
    }


def plot_results(
    config: dict,
    summary: pd.DataFrame,
    gate_frame: pd.DataFrame,
    task_frame: pd.DataFrame,
    stress_frame: pd.DataFrame | None,
    output: Path,
) -> list[Path]:
    figure_directory = output / "figures"
    figure_directory.mkdir(parents=True, exist_ok=True)
    colors = plt.get_cmap("viridis")(np.linspace(0.12, 0.88, len(summary)))
    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 7,
            "figure.dpi": 160,
            "savefig.dpi": 300,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    paths: list[Path] = []

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), constrained_layout=True)
    x = summary["s"].to_numpy()
    y = summary["jeffreys_mean"].to_numpy()
    yerr = np.vstack(
        [y - summary["jeffreys_ci_lower"], summary["jeffreys_ci_upper"] - y]
    )
    axes[0].errorbar(x, y, yerr=yerr, fmt="o", color="#2a6fbb", capsize=2, label="Exact-mixture MC")
    anchor_index = len(x) // 2
    reference = y[anchor_index] * (x / x[anchor_index]) ** 6
    axes[0].plot(x, reference, "--", color="#b84a3a", label=r"Reference $s^6$")
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Collision scale $s$")
    axes[0].set_ylabel("One-observation Jeffreys divergence")
    axes[0].set_title("(a) Sixth-order orientation information")
    axes[0].legend(frameon=False)

    axes[1].plot(x, summary["jeffreys_over_s6"], "o-", label=r"$J/s^6$", color="#2a6fbb")
    axes[1].plot(
        x,
        8.0 * summary["affinity_deficit_over_s6"],
        "s--",
        label=r"$8(1-A)/s^6$",
        color="#d28e2c",
    )
    axes[1].set_xlabel("Collision scale $s$")
    axes[1].set_ylabel("Scaled information")
    axes[1].set_title("(b) Stable local normalization")
    axes[1].legend(frameon=False)
    for suffix in ("pdf", "png"):
        path = figure_directory / f"orientation_sixth_order.{suffix}"
        fig.savefig(path, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(7.5, 2.75), constrained_layout=True)
    labels = {"parent": r"$I_G$", "support": r"$I_S$", "dictionary": r"$I_D=Ns^6$"}
    titles = {
        "parent": "(a) Parent gate",
        "support": "(b) Support gate",
        "dictionary": "(c) Dictionary gate",
    }
    for axis, gate in zip(axes, ("parent", "support", "dictionary")):
        subset = gate_frame[gate_frame["gate"] == gate]
        for color, (s, group) in zip(colors, subset.groupby("s", sort=True)):
            axis.plot(group["budget"], group["affinity"], color=color, marker="o", markersize=2.5, label=f"s={s:g}")
        axis.set_xscale("log")
        axis.set_xlabel(labels[gate])
        axis.set_title(titles[gate])
        axis.grid(alpha=0.18)
        axis.set_ylabel("Product affinity")
        axis.set_ylim(-0.02, 1.02)
    axes[-1].legend(frameon=False, ncol=2, loc="upper right")
    for suffix in ("pdf", "png"):
        path = figure_directory / f"three_gate_pairwise_curves.{suffix}"
        fig.savefig(path, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)

    display_s = min(config["confirmatory"]["s_grid"], key=lambda value: abs(value - 0.1))
    task_subset = task_frame[np.isclose(task_frame["s"], display_s)]
    fig, axis = plt.subplots(figsize=(4.6, 3.1), constrained_layout=True)
    task_colors = ["#333333", "#2a6fbb", "#d28e2c"]
    for color, (contrast, group) in zip(task_colors, task_subset.groupby("contrast", sort=True)):
        axis.plot(group["phi"], group["numerical_residual"], marker="o", markersize=2.5, color=color, label=f"contrast d={contrast:g}")
        if contrast:
            axis.plot(group["phi"], group["analytic_residual"], "--", color=color, linewidth=1)
    axis.set_xlabel(r"Rotation angle $\phi$")
    axis.set_ylabel("Coefficient-profiled test residual")
    axis.set_title(f"Task invariance and symmetry breaking (s={display_s:g})")
    axis.legend(frameon=False)
    axis.grid(alpha=0.18)
    for suffix in ("pdf", "png"):
        path = figure_directory / f"task_invariance.{suffix}"
        fig.savefig(path, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)

    if stress_frame is not None:
        pivot = stress_frame.pivot(index="nu", columns="p", values="slope").sort_index(ascending=False)
        fig, axis = plt.subplots(figsize=(4.5, 3.1), constrained_layout=True)
        image = axis.imshow(pivot.to_numpy(), vmin=5.4, vmax=6.6, cmap="RdYlBu_r", aspect="auto")
        axis.set_xticks(range(len(pivot.columns)), [f"{value:g}" for value in pivot.columns])
        axis.set_yticks(range(len(pivot.index)), [f"{value:g}" for value in pivot.index])
        axis.set_xlabel("Bernoulli activation p")
        axis.set_ylabel("Training noise variance nu")
        axis.set_title("Stress-grid fitted Jeffreys exponent")
        for i in range(len(pivot.index)):
            for j in range(len(pivot.columns)):
                axis.text(j, i, f"{pivot.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8)
        fig.colorbar(image, ax=axis, label="Log-log slope")
        for suffix in ("pdf", "png"):
            path = figure_directory / f"stress_exponents.{suffix}"
            fig.savefig(path, bbox_inches="tight")
            paths.append(path)
        plt.close(fig)
    return paths


def format_value(value) -> str:
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(format_value(item) for item in value) + "]"
    if isinstance(value, (float, np.floating)):
        return f"{value:.6g}"
    return str(value)


def write_markdown_report(
    path: Path,
    status: str,
    checks: list[dict],
    scaling: dict,
    gates: dict,
    task: dict,
    gh: dict,
    stress: dict | None,
    config: dict,
) -> None:
    lines = [
        "# Three-gate theorem-native simulation pilot",
        "",
        f"**Status: `{status}`**",
        "",
        "## Executive conclusion",
        "",
    ]
    if status == "GO_FOR_MANUSCRIPT_INTEGRATION":
        lines.append(
            "The frozen low-dimensional experiment passes the preregistered numerical gate. "
            "The exact Bernoulli-Gaussian mixture exhibits sixth-order orientation information, "
            "the dictionary curves collapse against `Ns^6`, and the equal-coefficient test law "
            "is invariant to machine precision.  These results support a short theorem-native "
            "numerical illustration, not a practical-algorithm or application claim."
        )
    else:
        failed = [item["check"] for item in checks if not item["pass"]]
        lines.append("The pilot did not clear every frozen requirement. Failed checks: " + "; ".join(failed) + ".")
    lines.extend(
        [
            "",
            "## Primary estimates",
            "",
            f"- Jeffreys log-log slope: `{scaling['jeffreys']['slope']:.4f}` "
            f"(paired bootstrap 95% CI `{scaling['jeffreys']['bootstrap_ci_lower']:.4f}` to "
            f"`{scaling['jeffreys']['bootstrap_ci_upper']:.4f}`).",
            f"- Affinity-deficit log-log slope: `{scaling['affinity_deficit']['slope']:.4f}` "
            f"(paired bootstrap 95% CI `{scaling['affinity_deficit']['bootstrap_ci_lower']:.4f}` to "
            f"`{scaling['affinity_deficit']['bootstrap_ci_upper']:.4f}`).",
            f"- Dictionary product-affinity maximum transition-band spread: "
            f"`{gates['maximum_vertical_spread']:.4g}`.",
            f"- Maximum equal-coefficient residual: `{task['maximum_equal_coefficient_residual']:.3e}`.",
            f"- Gauss-Hermite cross-check: `{'PASS' if gh['pass'] else 'FAIL'}`.",
            "",
            "## Frozen checks",
            "",
            "| Check | Value | Requirement | Result |",
            "|---|---:|---:|:---:|",
        ]
    )
    for item in checks:
        lines.append(
            f"| {item['check']} | {format_value(item['value'])} | "
            f"{item['relation']} {format_value(item['threshold'])} | "
            f"{'PASS' if item['pass'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Stress grid",
            "",
            "The stress grid was run only after the confirmatory evidence was available. "
            + (
                f"It {'passed' if stress and stress['pass'] else 'did not fully pass'} the broad exponent band; "
                f"slopes ranged from `{stress['minimum_slope']:.4f}` to `{stress['maximum_slope']:.4f}`."
                if stress
                else "It was not run because the confirmatory gate did not pass."
            ),
            "",
            "## Interpretation boundary",
            "",
            "All three gate panels use product affinity. For the parent and support pairs it is "
            "analytic under equal-covariance Gaussians; for the dictionary pair it is estimated "
            "from the one-observation 32-component mixture and raised to the Nth power exactly. "
            "The CSV also records exact parent/support Bayes errors and affinity-based dictionary "
            "Bayes-error bounds. None of these quantities is the output of the full robust moment "
            "correspondence. The simulation therefore demonstrates the information geometry only.",
            "",
            "## Reproducibility",
            "",
            f"- Protocol: `{config['protocol_version']}`.",
            f"- Confirmatory observations per collision scale: "
            f"`{config['confirmatory']['mc_batches'] * config['confirmatory']['mc_batch_size']:,}`.",
            f"- Confirmatory seed: `{config['confirmatory']['seed']}`.",
            "- Machine-readable results and all figure source data are included beside this report.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_pdf_report(
    path: Path,
    status: str,
    checks: list[dict],
    scaling: dict,
    gates: dict,
    task: dict,
    stress: dict | None,
    figure_directory: Path,
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Image,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold")
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "DejaVu"
    for heading in ("Title", "Heading1", "Heading2", "Heading3", "Heading4"):
        styles[heading].fontName = "DejaVu-Bold"
    styles.add(ParagraphStyle(name="CenteredTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=19, leading=23, textColor=colors.HexColor("#18324a"), fontName="DejaVu-Bold"))
    styles.add(ParagraphStyle(name="Status", parent=styles["Heading2"], alignment=TA_CENTER, fontSize=11, textColor=colors.HexColor("#1d6b45" if status.startswith("GO") else "#9b3a2d"), fontName="DejaVu-Bold"))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8.2, leading=10.5, fontName="DejaVu"))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("DejaVu", 8)
        canvas.setFillColor(colors.HexColor("#66717c"))
        canvas.drawString(0.7 * inch, 0.45 * inch, "THREE-GATE-SIM-PILOT-R0")
        canvas.drawRightString(A4[0] - 0.7 * inch, 0.45 * inch, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.65 * inch,
        title="Three-gate theorem-native simulation pilot",
        author="Simulation audit",
    )
    story = [
        Spacer(1, 0.15 * inch),
        Paragraph("Three-gate theorem-native<br/>simulation pilot", styles["CenteredTitle"]),
        Spacer(1, 0.08 * inch),
        Paragraph(status.replace("_", " "), styles["Status"]),
        Spacer(1, 0.22 * inch),
        Paragraph(
            "This frozen synthetic audit checks the manuscript's information geometry. "
            "It does not validate the conservative confidence profiler, a scalable algorithm, "
            "or an application embedding.",
            styles["BodyText"],
        ),
        Spacer(1, 0.18 * inch),
    ]
    headline = [
        ["Metric", "Estimate"],
        ["Jeffreys exponent", f"{scaling['jeffreys']['slope']:.4f}"],
        ["Affinity-deficit exponent", f"{scaling['affinity_deficit']['slope']:.4f}"],
        ["Dictionary collapse max spread", f"{gates['maximum_vertical_spread']:.4g}"],
        ["Equal-coefficient residual", f"{task['maximum_equal_coefficient_residual']:.3e}"],
        ["Stress slope range", f"{stress['minimum_slope']:.3f} to {stress['maximum_slope']:.3f}" if stress else "not run"],
    ]
    table = Table(headline, colWidths=[3.25 * inch, 2.1 * inch], repeatRows=1)
    table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "DejaVu"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe9f1")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#18324a")), ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"), ("FONTNAME", (0, 1), (0, -1), "DejaVu-Bold"), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aeb8c2")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]), ("FONTSIZE", (0, 0), (-1, -1), 9), ("LEADING", (0, 0), (-1, -1), 11), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.extend([table, Spacer(1, 0.2 * inch), Paragraph("Frozen adjudication checks", styles["Heading2"])])
    check_rows = [["Check", "Value", "Result"]]
    for item in checks:
        check_rows.append([Paragraph(item["check"], styles["Small"]), Paragraph(format_value(item["value"]), styles["Small"]), "PASS" if item["pass"] else "FAIL"])
    checks_table = Table(check_rows, colWidths=[3.35 * inch, 1.55 * inch, 0.65 * inch], repeatRows=1)
    checks_table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "DejaVu"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe9f1")), ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#b6c0c8")), ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (-1, 1), (-1, -1), "CENTER"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fa")])]))
    story.extend([checks_table, PageBreak()])
    figures = [
        ("Sixth-order orientation information", figure_directory / "orientation_sixth_order.png", 7.1 * inch, 2.95 * inch),
        ("Three pairwise information gates", figure_directory / "three_gate_pairwise_curves.png", 7.1 * inch, 2.62 * inch),
        ("Equal-coefficient invariance and contrast", figure_directory / "task_invariance.png", 5.0 * inch, 3.35 * inch),
    ]
    if (figure_directory / "stress_exponents.png").exists():
        figures.append(("Independent stress grid", figure_directory / "stress_exponents.png", 5.0 * inch, 3.35 * inch))
    for index, (title, image_path, width, height) in enumerate(figures):
        story.append(Paragraph(title, styles["Heading2"]))
        story.append(Spacer(1, 0.08 * inch))
        story.append(Image(str(image_path), width=width, height=height))
        story.append(Spacer(1, 0.12 * inch))
        if title.startswith("Three"):
            story.append(Paragraph("All panels use product affinity. Parent and support are analytic Gaussian pairs; dictionary uses the exact product law of the 32-component training-mixture affinity, avoiding infeasible finite-N LRT simulation.", styles["Small"]))
        elif title.startswith("Sixth"):
            story.append(Paragraph("Error bars are 95% t intervals across 128 paired blocks. The dashed line is an anchored s^6 reference, not a fitted curve.", styles["Small"]))
        elif title.startswith("Equal"):
            story.append(Paragraph("The solid curves are numerical coefficient-profiled residuals; dashed curves are the closed-form two-atom contrast identity.", styles["Small"]))
        else:
            story.append(Paragraph("The stress grid changes the activation probability and training-noise variance. It audits exponent robustness, not equality of constants.", styles["Small"]))
        if index < len(figures) - 1:
            story.append(PageBreak())
    document.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--output", type=Path, default=Path("results"))
    arguments = parser.parse_args()
    config_path = arguments.config.resolve()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = read_json(config_path)
    repository_root = config_path.parent

    def portable(path: Path) -> str:
        try:
            return path.relative_to(repository_root).as_posix()
        except ValueError:
            return str(path)

    batches, summary, scaling = run_confirmatory(config, output)
    gh_frame, gh_metrics = run_gauss_hermite(config, summary, output)
    gate_frame, gate_metrics = run_gate_curves(config, summary, output)
    task_frame, matching_frame, task_metrics = run_task_controls(config, output)
    status, checks = adjudicate(
        config, summary, scaling, gate_metrics, task_metrics, gh_metrics
    )

    stress_frame = None
    stress_metrics = None
    if status == "GO_FOR_MANUSCRIPT_INTEGRATION" and config["stress"]["enabled_after_confirmatory_pass"]:
        stress_frame, stress_metrics = run_stress(config, output)

    figures = plot_results(config, summary, gate_frame, task_frame, stress_frame, output)
    report_path = output / "THREE_GATE_SIMULATION_PILOT_REPORT.md"
    write_markdown_report(
        report_path,
        status,
        checks,
        scaling,
        gate_metrics,
        task_metrics,
        gh_metrics,
        stress_metrics,
        config,
    )
    pdf_directory = output.parent / "output" / "pdf"
    pdf_directory.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_directory / "THREE_GATE_SIMULATION_PILOT_REPORT.pdf"
    build_pdf_report(
        pdf_path,
        status,
        checks,
        scaling,
        gate_metrics,
        task_metrics,
        stress_metrics,
        output / "figures",
    )

    metrics = {
        "status": status,
        "checks": checks,
        "scaling": scaling,
        "gate_collapse": gate_metrics,
        "task_controls": task_metrics,
        "gauss_hermite": gh_metrics,
        "stress": stress_metrics,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "pandas": pd.__version__,
        },
        "inputs": {
            "config_sha256": checksum(config_path),
        },
        "outputs": {
            "report_markdown": portable(report_path),
            "report_pdf": portable(pdf_path),
            "figures": [portable(path) for path in figures],
        },
    }
    write_json(output / "adjudication.json", metrics)
    print(json.dumps({"status": status, "report": str(report_path), "pdf": str(pdf_path)}, indent=2))
    return 0 if status == "GO_FOR_MANUSCRIPT_INTEGRATION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
