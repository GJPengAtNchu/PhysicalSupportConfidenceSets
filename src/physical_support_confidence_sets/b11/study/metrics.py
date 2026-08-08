"""Frozen fresh-effectiveness and empirical-risk aggregation."""

from __future__ import annotations

from collections import Counter
import math
from statistics import median
from typing import Any, Iterable

from scipy.stats import beta, binomtest

from .constants import PROFILE_PARAMETERS, PROFILES


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def effectiveness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    ambiguous = [
        row for row in rows if row.get("oracle_label") == "ORACLE_AMBIGUOUS"
    ]
    fine = [row for row in rows if row.get("oracle_label") == "ORACLE_FINE"]
    nonambiguous = [
        row
        for row in rows
        if row.get("oracle_label") in {"ORACLE_FINE", "ORACLE_SECTOR"}
    ]
    outputs = Counter(row["output"] for row in rows)
    fractions = [float(row["query_fraction"]) for row in rows]
    return {
        "n": total,
        "oracle_ambiguous_n": len(ambiguous),
        "oracle_fine_n": len(fine),
        "oracle_nonambiguous_n": len(nonambiguous),
        "outputs": dict(sorted(outputs.items())),
        "ambiguous_recall": _ratio(
            sum(row["output"] == "AMBIGUOUS" for row in ambiguous),
            len(ambiguous),
        ),
        "fine_recall": _ratio(
            sum(row["output"] == "FINE" for row in fine), len(fine)
        ),
        "safe_nonambiguous_rate": _ratio(
            sum(
                row["output"] in {"FINE", "SECTOR_SAFE"}
                for row in nonambiguous
            ),
            len(nonambiguous),
        ),
        "nonabstain_yield": _ratio(
            sum(row["output"] != "ABSTAIN" for row in rows), total
        ),
        "abstain_rate": _ratio(
            sum(row["output"] == "ABSTAIN" for row in rows), total
        ),
        "median_query_fraction": median(fractions) if fractions else None,
        "worst_query_fraction": max(fractions) if fractions else None,
    }


def aggregate_frontier(
    enriched: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    budgets = sorted({float(row["budget_fraction"]) for row in enriched})
    conditions = sorted({row["condition"] for row in enriched})
    for scope, profile, condition in (
        [("POOLED", "ALL", "ALL")]
        + [
            ("PROFILE", name, "ALL")
            for name in sorted({row["profile"] for row in enriched})
        ]
        + [
            ("CONDITION", "ALL", name)
            for name in conditions
        ]
        + [
            ("PROFILE_CONDITION", profile_name, condition_name)
            for profile_name in sorted(
                {row["profile"] for row in enriched}
            )
            for condition_name in conditions
        ]
    ):
        for budget in budgets:
            selected = [
                row
                for row in enriched
                if float(row["budget_fraction"]) == budget
                and (profile == "ALL" or row["profile"] == profile)
                and (condition == "ALL" or row["condition"] == condition)
            ]
            if not selected:
                continue
            metric = effectiveness(selected)
            output.append(
                {
                    "scope": scope,
                    "profile": profile,
                    "condition": condition,
                    "budget_fraction": budget,
                    **{
                        key: (
                            str(value)
                            if isinstance(value, dict)
                            else value
                        )
                        for key, value in metric.items()
                    },
                }
            )
    return output


def clopper_pearson(
    errors: int, total: int, confidence: float = 0.95
) -> tuple[float | None, float | None]:
    if total == 0:
        return None, None
    tail = (1.0 - confidence) / 2.0
    lower = 0.0 if errors == 0 else float(beta.ppf(tail, errors, total - errors + 1))
    upper = (
        1.0
        if errors == total
        else float(beta.ppf(1.0 - tail, errors + 1, total - errors))
    )
    return lower, upper


def empirical_risk_rows(
    enriched: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for profile in PROFILES:
        alpha = PROFILE_PARAMETERS[profile][0]
        for budget in sorted(
            {float(row["budget_fraction"]) for row in enriched}
        ):
            rows = [
                row
                for row in enriched
                if row["profile"] == profile
                and float(row["budget_fraction"]) == budget
            ]
            n = len(rows)
            wrong_fine = sum(
                row["output"] == "FINE" and row["truth_wrong_fine"]
                for row in rows
            )
            wrong_sector = sum(
                row["output"] in {"FINE", "SECTOR_SAFE"}
                and row["truth_wrong_sector"]
                for row in rows
            )
            fine_selected = [row for row in rows if row["output"] == "FINE"]
            sector_selected = [
                row
                for row in rows
                if row["output"] in {"FINE", "SECTOR_SAFE"}
            ]
            fine_cp = clopper_pearson(wrong_fine, n)
            sector_cp = clopper_pearson(wrong_sector, n)
            output.append(
                {
                    "profile": profile,
                    "alpha": alpha,
                    "budget_fraction": budget,
                    "n": n,
                    "wrong_fine_count": wrong_fine,
                    "wrong_fine_marginal_rate": _ratio(wrong_fine, n),
                    "wrong_fine_cp95_lower": fine_cp[0],
                    "wrong_fine_cp95_upper": fine_cp[1],
                    "wrong_fine_selective_n": len(fine_selected),
                    "wrong_fine_selective_rate": _ratio(
                        sum(row["truth_wrong_fine"] for row in fine_selected),
                        len(fine_selected),
                    ),
                    "wrong_fine_one_sided_p": (
                        float(
                            binomtest(
                                wrong_fine,
                                n,
                                p=alpha,
                                alternative="greater",
                            ).pvalue
                        )
                        if n
                        else None
                    ),
                    "wrong_sector_count": wrong_sector,
                    "wrong_sector_marginal_rate": _ratio(wrong_sector, n),
                    "wrong_sector_cp95_lower": sector_cp[0],
                    "wrong_sector_cp95_upper": sector_cp[1],
                    "wrong_sector_selective_n": len(sector_selected),
                    "wrong_sector_selective_rate": _ratio(
                        sum(
                            row["truth_wrong_sector"]
                            for row in sector_selected
                        ),
                        len(sector_selected),
                    ),
                    "wrong_sector_one_sided_p": (
                        float(
                            binomtest(
                                wrong_sector,
                                n,
                                p=alpha,
                                alternative="greater",
                            ).pvalue
                        )
                        if n
                        else None
                    ),
                    "gross_excess_reject_0_05": (
                        bool(
                            n
                            and (
                                binomtest(
                                    wrong_fine,
                                    n,
                                    p=alpha,
                                    alternative="greater",
                                ).pvalue
                                < 0.05
                                or binomtest(
                                    wrong_sector,
                                    n,
                                    p=alpha,
                                    alternative="greater",
                                ).pvalue
                                < 0.05
                            )
                        )
                    ),
                }
            )
    return output


def adjudicate(
    enriched: list[dict[str, Any]],
    oracle_results: list[dict[str, Any]],
    safety_findings: list[dict[str, Any]],
    risk_rows: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    completed = [row for row in oracle_results if row["complete"]]
    completed_by_condition = Counter(row["condition"] for row in completed)
    structural_unsafe = sum(
        row["kind"] == "STRUCTURAL_UNSAFE_OUTPUT"
        for row in safety_findings
    )
    bound_violations = sum(
        row["kind"] == "BOUND_VIOLATION" for row in safety_findings
    )
    exhaustive_mismatches = sum(
        row["kind"] == "EXHAUSTIVE_LABEL_MISMATCH"
        for row in safety_findings
    )
    at_050 = [
        row for row in enriched if float(row["budget_fraction"]) == 0.50
    ]
    at_075 = [
        row for row in enriched if float(row["budget_fraction"]) == 0.75
    ]
    metric_050 = effectiveness(at_050)
    metric_075 = effectiveness(at_075)
    outputs_075 = set(row["output"] for row in at_075)
    risk_excess = any(
        row["gross_excess_reject_0_05"]
        for row in risk_rows
        if float(row["budget_fraction"]) == 0.75
    )
    gates = {
        "dataset_count": len({row["case_id"] for row in enriched}) == 18,
        "trace_count": len(
            {
                (row["case_id"], row["profile"])
                for row in enriched
            }
        )
        == 54,
        "oracle_coverage": len(completed) >= 16
        and all(value >= 5 for value in completed_by_condition.values())
        and len(completed_by_condition) == 3,
        "zero_structural_unsafe": structural_unsafe == 0,
        "zero_bound_violations": bound_violations == 0,
        "exhaustive_equality": exhaustive_mismatches == 0,
        "ambiguity_recall_050": (
            metric_050["ambiguous_recall"] is not None
            and metric_050["ambiguous_recall"] >= 0.85
        ),
        "nonabstain_075": (
            metric_075["nonabstain_yield"] is not None
            and metric_075["nonabstain_yield"] >= 0.85
        ),
        "safe_nonambiguous_075": (
            metric_075["safe_nonambiguous_rate"] is not None
            and metric_075["safe_nonambiguous_rate"] >= 0.80
        ),
        "fine_recall_075": (
            metric_075["fine_recall"] is not None
            and metric_075["fine_recall"] >= 0.30
        ),
        "all_three_outputs_075": {
            "FINE",
            "SECTOR_SAFE",
            "AMBIGUOUS",
        }.issubset(outputs_075),
        "query_cost_075": (
            metric_075["median_query_fraction"] is not None
            and metric_075["median_query_fraction"] <= 0.65
        ),
        "no_gross_empirical_risk_excess": not risk_excess,
    }
    if structural_unsafe:
        status = "FAIL_ARA_B1_UNSAFE_DECISION"
    elif bound_violations:
        status = "FAIL_ARA_B1_BOUND_INVARIANT"
    elif exhaustive_mismatches:
        status = "FAIL_ARA_B1_EXHAUSTIVE_LABEL_MISMATCH"
    elif not gates["oracle_coverage"]:
        status = "HOLD_ARA_B1_ORACLE_COVERAGE_INSUFFICIENT"
    elif not gates["ambiguity_recall_050"]:
        status = "HOLD_ARA_B1_AMBIGUITY_DETECTION_INSUFFICIENT"
    elif not (
        gates["nonabstain_075"]
        and gates["safe_nonambiguous_075"]
        and gates["fine_recall_075"]
        and gates["all_three_outputs_075"]
    ):
        status = "HOLD_ARA_B1_UPPER_CERTIFICATION_INSUFFICIENT"
    elif not gates["query_cost_075"]:
        status = "HOLD_ARA_B1_QUERY_COST_TOO_HIGH"
    elif risk_excess:
        status = "HOLD_ARA_B1_EMPIRICAL_RISK_EXCESS"
    elif all(gates.values()):
        status = "PASS_ARA_B1_FRESH_GLOBAL_CONTROLLER_VALIDATED"
    else:
        status = "HOLD_ARA_B1_FRESH_GENERALIZATION_INCONCLUSIVE"
    return status, {
        "gates": gates,
        "completed_oracles": len(completed),
        "completed_by_condition": dict(completed_by_condition),
        "structural_unsafe_count": structural_unsafe,
        "bound_violation_count": bound_violations,
        "exhaustive_label_mismatch_count": exhaustive_mismatches,
        "budget_0_50": metric_050,
        "budget_0_75": metric_075,
        "gross_empirical_risk_excess": risk_excess,
    }
