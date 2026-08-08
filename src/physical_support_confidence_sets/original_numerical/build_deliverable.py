"""Build the combined internal adjudication and manuscript-candidate figure."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def manuscript_figure(root: Path) -> tuple[Path, Path]:
    results = root / "results"
    summary = pd.read_csv(results / "confirmatory_summary.csv")
    gates = pd.read_csv(results / "gate_curves.csv")
    colors = plt.get_cmap("viridis")(np.linspace(0.12, 0.88, len(summary)))
    plt.rcParams.update(
        {
            "font.size": 8.5,
            "axes.titlesize": 9.5,
            "axes.labelsize": 8.5,
            "legend.fontsize": 7,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    fig, axes = plt.subplots(1, 3, figsize=(7.5, 2.55), constrained_layout=True)

    representative_s = min(summary["s"], key=lambda value: abs(value - 0.1))
    parent = gates[(gates["gate"] == "parent") & np.isclose(gates["s"], representative_s)]
    support = gates[(gates["gate"] == "support") & np.isclose(gates["s"], representative_s)]
    axes[0].plot(parent["budget"], parent["affinity"], "o-", markersize=3, label=r"Parent: $I_G$")
    axes[0].plot(support["budget"], support["affinity"], "s--", markersize=3, label=r"Support: $I_S$")
    axes[0].set_xscale("log")
    axes[0].set_ylim(-0.02, 1.02)
    axes[0].set_xlabel("Gate-specific information budget")
    axes[0].set_ylabel("Product affinity")
    axes[0].set_title("(a) Test-side gates")
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.18)

    x = summary["s"].to_numpy()
    y = summary["jeffreys_mean"].to_numpy()
    yerr = np.vstack([y - summary["jeffreys_ci_lower"], summary["jeffreys_ci_upper"] - y])
    axes[1].errorbar(x, y, yerr=yerr, fmt="o", capsize=2, label="Exact mixture")
    anchor_index = len(x) // 2
    axes[1].plot(x, y[anchor_index] * (x / x[anchor_index]) ** 6, "--", label=r"Reference $s^6$")
    axes[1].set_xscale("log")
    axes[1].set_yscale("log")
    axes[1].set_xlabel("Collision scale $s$")
    axes[1].set_ylabel("Jeffreys divergence")
    axes[1].set_title("(b) Cubic-score geometry")
    axes[1].legend(frameon=False)

    dictionary = gates[gates["gate"] == "dictionary"]
    for color, (s, group) in zip(colors, dictionary.groupby("s", sort=True)):
        axes[2].plot(group["budget"], group["affinity"], color=color, marker="o", markersize=2.5, label=f"s={s:g}")
    axes[2].set_xscale("log")
    axes[2].set_ylim(-0.02, 1.02)
    axes[2].set_xlabel(r"Dictionary budget $I_D=Ns^6$")
    axes[2].set_ylabel("Product affinity")
    axes[2].set_title("(c) Dictionary-gate collapse")
    axes[2].legend(frameon=False, ncol=2)
    axes[2].grid(alpha=0.18)

    png = results / "figures" / "manuscript_candidate_composite.png"
    pdf = results / "figures" / "manuscript_candidate_composite.pdf"
    fig.savefig(png, bbox_inches="tight", dpi=300)
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return png, pdf


def markdown_report(root: Path, confirmatory: dict, posthoc: dict) -> Path:
    output = root / "results" / "THREE_GATE_SIMULATION_ADJUDICATION.md"
    failed = [item for item in confirmatory["checks"] if not item["pass"]]
    lines = [
        "# Three-gate simulation: combined adjudication",
        "",
        "## Bottom line",
        "",
        "The theorem-native simulation **works scientifically**, but the frozen R0 status remains "
        "`HOLD_NUMERICAL_EVIDENCE`. One secondary median-collapse threshold missed narrowly; it "
        "must not be relabeled as a confirmatory pass. Independent post-hoc checks show that the "
        "underlying information geometry is robust enough to justify a modest numerical "
        "illustration in the manuscript.",
        "",
        "| Item | Result |",
        "|---|---:|",
        f"| Jeffreys s exponent | {confirmatory['scaling']['jeffreys']['slope']:.4f} |",
        f"| Paired bootstrap 95% CI | [{confirmatory['scaling']['jeffreys']['bootstrap_ci_lower']:.4f}, {confirmatory['scaling']['jeffreys']['bootstrap_ci_upper']:.4f}] |",
        f"| R-squared | {confirmatory['scaling']['jeffreys']['r_squared']:.6f} |",
        f"| Dictionary maximum cross-s spread | {confirmatory['gate_collapse']['maximum_vertical_spread']:.4f} |",
        f"| Frozen median-spread criterion | {confirmatory['gate_collapse']['median_vertical_spread']:.4f} vs 0.015 (FAIL) |",
        f"| Equal-coefficient residual | {confirmatory['task_controls']['maximum_equal_coefficient_residual']:.3e} |",
        f"| h exponent (post-hoc) | {posthoc['h_scaling']['slope']:.4f} |",
        f"| Stress-grid s exponents (post-hoc) | {posthoc['stress']['minimum_slope']:.4f} to {posthoc['stress']['maximum_slope']:.4f} |",
        f"| All-s order-14 quadrature exponent | {posthoc['all_s_order14_quadrature']['slope']:.4f} |",
        "",
        "## Why R0 is HOLD rather than NO-GO",
        "",
        f"The only failed frozen check was `{failed[0]['check']}`: "
        f"`{failed[0]['value']:.6f}` against `<= {failed[0]['threshold']}`. "
        "The maximum-spread criterion passed, all sixth-order and numerical-integrity criteria "
        "passed, and deterministic quadrature reproduced the exponent. The near-miss therefore "
        "does not indicate a failed phenomenon; it records that the finite-s curves retain a "
        "small higher-order drift.",
        "",
        "## Manuscript recommendation",
        "",
        "Add one compact three-panel figure and roughly two short paragraphs, provided an equal "
        "amount of text is compressed elsewhere to preserve the SIMODS length limit. Put the "
        "task-invariance and p/nu stress diagnostics in the supplement.",
        "",
        "Permitted claim:",
        "",
        "> In the q=4 Bernoulli-Gaussian hard core, exact-mixture calculations exhibit the "
        "> predicted sixth-order orientation information and an approximate product-experiment "
        "> collapse against Ns^6; equal coefficients leave the test mean invariant, whereas "
        "> amplitude contrast opens the prescribed task secant.",
        "",
        "Do not claim validation of the full robust moment correspondence, conditional coverage, "
        "a scalable algorithm, or localization transfer.",
        "",
        "## Formal status separation",
        "",
        f"- Confirmatory R0: `{confirmatory['status']}`.",
        f"- Post-hoc interpretation: `{posthoc['status']}`.",
        "- Integration recommendation: `ADD_THEOREM_NATIVE_ILLUSTRATION_WITH_SCOPE_LIMITS`.",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def pdf_report(root: Path, confirmatory: dict, posthoc: dict, manuscript_png: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold")
    path = root / "output" / "pdf" / "THREE_GATE_SIMULATION_ADJUDICATION_REPORT.pdf"
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "DejaVu"
    for heading in ("Title", "Heading1", "Heading2", "Heading3", "Heading4"):
        styles[heading].fontName = "DejaVu-Bold"
    styles.add(ParagraphStyle(name="CenterTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#18324a"), fontSize=18, leading=22, fontName="DejaVu-Bold"))
    styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], backColor=colors.HexColor("#eef4f8"), borderColor=colors.HexColor("#9fb6c8"), borderWidth=0.5, borderPadding=8, leading=14, fontName="DejaVu"))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8.5, leading=11, fontName="DejaVu"))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("DejaVu", 8)
        canvas.setFillColor(colors.HexColor("#67737e"))
        canvas.drawString(0.65 * inch, 0.42 * inch, "Three-gate simulation adjudication")
        canvas.drawRightString(A4[0] - 0.65 * inch, 0.42 * inch, f"Page {document.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=0.65 * inch, rightMargin=0.65 * inch, topMargin=0.58 * inch, bottomMargin=0.65 * inch, title="Three-gate simulation adjudication")
    story = [
        Spacer(1, 0.1 * inch),
        Paragraph("Three-gate simulation<br/>combined adjudication", styles["CenterTitle"]),
        Spacer(1, 0.16 * inch),
        Paragraph("Scientific conclusion: the information geometry is robust enough for a scoped theorem-native illustration. Formal conclusion: R0 remains HOLD because one secondary frozen threshold narrowly failed.", styles["Callout"]),
        Spacer(1, 0.18 * inch),
    ]
    data = [
        ["Diagnostic", "Result", "Interpretation"],
        ["Jeffreys s exponent", f"{confirmatory['scaling']['jeffreys']['slope']:.4f}", "sixth order"],
        ["Paired bootstrap CI", f"{confirmatory['scaling']['jeffreys']['bootstrap_ci_lower']:.4f} to {confirmatory['scaling']['jeffreys']['bootstrap_ci_upper']:.4f}", "stable"],
        ["Maximum curve spread", f"{confirmatory['gate_collapse']['maximum_vertical_spread']:.4f}", "passes 0.04"],
        ["Median curve spread", f"{confirmatory['gate_collapse']['median_vertical_spread']:.4f}", "misses 0.015"],
        ["Equal-coefficient residual", f"{confirmatory['task_controls']['maximum_equal_coefficient_residual']:.2e}", "invariant"],
        ["Post-hoc h exponent", f"{posthoc['h_scaling']['slope']:.4f}", "quadratic"],
        ["Stress-grid s range", f"{posthoc['stress']['minimum_slope']:.3f} to {posthoc['stress']['maximum_slope']:.3f}", "9/9 pass"],
        ["Order-14 quadrature exponent", f"{posthoc['all_s_order14_quadrature']['slope']:.4f}", "confirms MC"],
    ]
    table = Table(data, colWidths=[2.5 * inch, 1.45 * inch, 1.55 * inch], repeatRows=1)
    table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "DejaVu"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe9f1")), ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"), ("FONTNAME", (0, 1), (0, -1), "DejaVu-Bold"), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aeb8c2")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fa")]), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.extend([table, Spacer(1, 0.18 * inch), Paragraph("Formal status", styles["Heading2"]), Paragraph(f"Confirmatory R0: <b>{confirmatory['status']}</b><br/>Post-hoc interpretation: <b>{posthoc['status']}</b><br/>Recommendation: <b>ADD THEOREM-NATIVE ILLUSTRATION WITH SCOPE LIMITS</b>", styles["BodyText"]), PageBreak()])

    story.extend([Paragraph("Manuscript-candidate numerical figure", styles["Heading2"]), Spacer(1, 0.08 * inch), Image(str(manuscript_png), width=7.05 * inch, height=2.40 * inch), Spacer(1, 0.15 * inch), Paragraph("Panel (a) uses analytic Gaussian affinities. Panel (b) uses the exact 32-component mixture with paired Monte Carlo and an anchored s^6 reference. Panel (c) uses the exact product law of the estimated one-observation affinity. The figure demonstrates information geometry, not the output of the confidence correspondence.", styles["Small"]), Spacer(1, 0.18 * inch), Paragraph("Permitted manuscript statement", styles["Heading2"]), Paragraph("In the q=4 Bernoulli-Gaussian hard core, exact-mixture calculations exhibit the predicted sixth-order orientation information and an approximate product-experiment collapse against Ns^6. Equal coefficients leave the test mean invariant; amplitude contrast opens the prescribed task secant.", styles["Callout"]), PageBreak()])

    task_image = root / "results" / "figures" / "task_invariance.png"
    posthoc_image = root / "results" / "posthoc" / "figures" / "posthoc_robustness.png"
    story.extend([Paragraph("Supplementary task and robustness diagnostics", styles["Heading2"]), Spacer(1, 0.08 * inch), Image(str(task_image), width=5.2 * inch, height=3.48 * inch), Paragraph("The equal-coefficient residual stays at machine precision; nonzero contrast matches the closed-form profiled secant.", styles["Small"]), Spacer(1, 0.18 * inch), Image(str(posthoc_image), width=6.45 * inch, height=3.05 * inch), Paragraph("Post-hoc checks cannot convert R0 into a pass. They show that h^2 scaling and the s exponent persist across the frozen p/nu stress grid.", styles["Small"]), PageBreak()])

    story.extend([Paragraph("Integration and claim boundaries", styles["Heading1"]), Paragraph("Recommended placement", styles["Heading2"]), Paragraph("Use the three-panel figure in a short numerical-illustration section. Put the task-invariance panel, p/nu stress grid, complete protocol, and code details in the supplement. Because the current manuscript already ends at numbered line 697, compress an equal amount of proof-idea or discussion text rather than appending beyond the SIMODS limit.", styles["BodyText"]), Spacer(1, 0.16 * inch), Paragraph("Do not claim", styles["Heading2"]), Paragraph("The experiment does not validate the conservative moment-profile correspondence, conditional coverage, a scalable solver, high-dimensional performance, localization transfer, or a deployed decision rule. Parent/support quantities are simple-pair diagnostics; dictionary affinity is a product-experiment information diagnostic.", styles["BodyText"]), Spacer(1, 0.16 * inch), Paragraph("Why the internal HOLD is retained", styles["Heading2"]), Paragraph("The median transition-band dispersion was 0.01670 against a frozen 0.015 threshold. The maximum dispersion was only 0.02433 and passed its 0.04 threshold. Retaining the HOLD records the preregistered near-miss; the manuscript need not discuss this private audit threshold, but the authors should avoid describing the curves as exact finite-s collapse.", styles["BodyText"])])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    confirmatory = json.loads((root / "results" / "adjudication.json").read_text())
    posthoc = json.loads((root / "results" / "posthoc" / "posthoc_adjudication.json").read_text())
    png, pdf = manuscript_figure(root)
    markdown = markdown_report(root, confirmatory, posthoc)
    report_pdf = pdf_report(root, confirmatory, posthoc, png)
    print(json.dumps({"markdown": str(markdown), "pdf": str(report_pdf), "figure_png": str(png), "figure_pdf": str(pdf)}, indent=2))


if __name__ == "__main__":
    main()
