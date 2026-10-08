"""Compares baseline vs advanced evaluation results and outputs markdown/rich tables."""

import json
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()


def generate_comparison_report(
    initial_path: Path = Path("evaluation/results_initial.json"),
    advanced_path: Path = Path("evaluation/results_advanced.json"),
    output_md_path: Path | None = Path("docs/evaluation_report.md"),
) -> str:
    with open(initial_path, "r", encoding="utf-8") as f:
        initial = json.load(f)
    with open(advanced_path, "r", encoding="utf-8") as f:
        advanced = json.load(f)

    init_m = initial["metrics"]
    adv_m = advanced["metrics"]

    # Metrics table
    console.print("\n" + "=" * 70)
    console.print("[bold green]BEFORE-AND-AFTER EVALUATION COMPARISON[/bold green]")
    console.print("=" * 70)

    rich_table = Table(title="Overall Metrics Comparison", header_style="bold blue")
    rich_table.add_column("Metric", style="cyan")
    rich_table.add_column("Baseline (V1)", justify="right", style="yellow")
    rich_table.add_column("LangGraph + Tools (V2)", justify="right", style="bold green")
    rich_table.add_column("Delta", justify="right", style="bold magenta")

    metrics_list = [
        ("Status Decision Accuracy", "status_accuracy", True),
        ("Disallowed Amount Accuracy", "disallowed_amount_accuracy", True),
        ("Policy Citation Recall", "citation_recall", True),
        ("Overall Deterministic Pass Rate", "overall_pass_rate", True),
        ("LLM Judge Groundedness (1-5)", "llm_judge_groundedness_avg", False),
        ("LLM Judge Actionability (1-5)", "llm_judge_actionability_avg", False),
        ("LLM Judge Agreement Rate", "llm_judge_agreement_rate", True),
    ]

    md_lines = [
        "# Evaluation Report: Before-and-After Compliance Audit Progression",
        "",
        "## 1. Executive Summary & Core Results",
        "",
        "This evaluation benchmarks the enterprise expense policy auditor following the **Build → Evaluate → Learn → Improve** cycle.",
        "We evaluated **25 curated, realistic expense claims** across 5 distinct operational slices (clean compliant, clear violations, transit edge cases, client entertainment documentation, and subtle evasions/math).",
        "",
        "| Metric | Baseline Agent (V1) | Improved LangGraph Agent (V2) | Improvement / Delta |",
        "| :--- | :---: | :---: | :---: |",
    ]

    for label, key, is_pct in metrics_list:
        v1 = init_m[key]
        v2 = adv_m[key]
        delta = v2 - v1

        if is_pct:
            v1_str = f"{v1*100:.1f}%"
            v2_str = f"{v2*100:.1f}%"
            d_str = f"+{delta*100:.1f}%" if delta >= 0 else f"{delta*100:.1f}%"
        else:
            v1_str = f"{v1:.2f} / 5.0"
            v2_str = f"{v2:.2f} / 5.0"
            d_str = f"+{delta:.2f}" if delta >= 0 else f"{delta:.2f}"

        rich_table.add_row(label, v1_str, v2_str, d_str)
        md_lines.append(f"| **{label}** | {v1_str} | **{v2_str}** | `{d_str}` |")

    console.print(rich_table)

    # Slice Breakdown
    md_lines.extend([
        "",
        "## 2. Performance Breakdown by Operational Slice",
        "",
        "| Evaluation Slice | Total Claims | Baseline Pass Rate | Improved Pass Rate | Delta | Key Nuance Tested |",
        "| :--- | :---: | :---: | :---: | :---: | :--- |",
    ])

    slice_descriptions = {
        "clean_compliant": "Clean compliant individual meals, subway, corporate hotel, client dinner.",
        "clear_violations": "Alcohol >20% cap, solo meal >$75 per diem, unauthorized rideshare, personal incidentals.",
        "transit_edge_cases": "Late-night exception (22:00-06:00), heavy equipment (>30 lbs), weather excuses, 14m vs 16m cutoff.",
        "client_entertainment_and_docs": "Mandatory attendee lists, vague justifications, non-itemized receipts above/below $25.",
        "subtle_evasions_and_math": "Same-day receipt splitting, disguised alcohol, breakfast/lunch solo drinks, multi-meal sum.",
    }

    slice_table = Table(title="Slice Performance Comparison", header_style="bold magenta")
    slice_table.add_column("Slice", style="white")
    slice_table.add_column("Total", justify="right")
    slice_table.add_column("Baseline Pass", justify="right", style="yellow")
    slice_table.add_column("Improved Pass", justify="right", style="bold green")
    slice_table.add_column("Delta", justify="right", style="bold cyan")

    for s_name in initial["slice_analysis"].keys():
        s_init = initial["slice_analysis"][s_name]
        s_adv = advanced["slice_analysis"][s_name]
        tot = s_init["total"]
        p1 = (s_init["overall_pass"] / tot) * 100
        p2 = (s_adv["overall_pass"] / tot) * 100
        d_slice = p2 - p1
        desc = slice_descriptions.get(s_name, "")

        slice_table.add_row(s_name, str(tot), f"{p1:.1f}%", f"{p2:.1f}%", f"+{d_slice:.1f}%")
        md_lines.append(
            f"| `{s_name}` | {tot} | {p1:.1f}% | **{p2:.1f}%** | `+{d_slice:.1f}%` | {desc} |"
        )

    console.print(slice_table)

    md_lines.extend([
        "",
        "## 3. What Did We Learn from Baseline Evaluation Failures?",
        "",
        "### Failure Mode 1: Arithmetic & Cap Double-Counting (TC-06)",
        "- **What happened**: The baseline agent reviewed a $130 meal with $45 alcohol ($25 excess alcohol). It disallowed $25 for alcohol, and then additionally disallowed $30 for per diem, double counting the food/drink deduction.",
        "- **The fix**: Implemented `audit_meals_and_per_diem()` in `src/expense_auditor/tools/math_tools.py` which sequences deductions deterministically: alcohol excess is calculated first, subtracted from eligible receipts, and then daily per diem ($75) is enforced on the remaining balance without double-penalty.",
        "",
        "### Failure Mode 2: Pre-tax vs Post-tax Deduction Confusion on Lodging (TC-10)",
        "- **What happened**: For a $350/night hotel room where the policy limit was $200 pre-tax, the baseline agent disallowed $150 room rate plus an invented $21 proportional tax, resulting in inconsistent accounting figures.",
        "- **The fix**: Implemented deterministic rate cap checking in `audit_lodging_and_incidentals()`, enforcing exact rule boundaries on pre-tax lodging rates.",
        "",
        "### Failure Mode 3: Geographic & Market Tier Misclassification (TC-09)",
        "- **What happened**: The baseline agent failed to identify Washington D.C. as a Tier 1 metropolitan area when destination was specified by hotel name rather than explicit state code.",
        "- **The fix**: Added multi-field context inspection (matching `origin`, `destination`, and `trip_purpose`) against canonical Tier 1 metropolitan markers in `math_tools.py`.",
        "",
        "### Failure Mode 4: Solo Per Diem vs Client Entertainment Confusion (TC-03, TC-20)",
        "- **What happened**: The baseline agent occasionally applied the $75 individual per diem rule to client hosting dinners.",
        "- **The fix**: Segmented meal audit logic so `CLIENT_ENTERTAINMENT` claims are strictly audited under SEC-3.2 ($150 per attendee) rather than SEC-1.1 ($75 individual per diem).",
        "",
        "## 4. Production Evaluation & Monitoring Strategy",
        "",
        "To safely transition this agent into production at enterprise scale:",
        "1. **Shadow Mode Deployment (Weeks 1-4)**:",
        "   - The auditor runs silently in parallel with human expense analysts on 100% of employee submissions.",
        "   - Compute the human-agent agreement matrix. Track false positives (disallowing compliant claims) and false negatives (approving non-compliant claims).",
        "2. **Confidence-Tiered Human-in-the-Loop Triage (Month 2+)**:",
        "   - **Auto-Approve Tier**: Reports under $100 with 100% itemized receipts, no alcohol, and high confidence (>0.95) are auto-approved instantly.",
        "   - **Review Tier**: Any report with detected violations or missing documentation is routed to finance staff with a pre-populated audit summary and employee remediation message ready for one-click approval.",
        "3. **Online LangSmith Monitoring & Continuous Drift Detection**:",
        "   - Sample 10% of production traces for automated LLM-as-a-judge evaluation (Groundedness & Actionability).",
        "   - Monitor employee appeal rates: any appealed audit is flagged as a high-value edge case to expand the regression test suite.",
        "   - Policy versioning: whenever company policies update, the automated eval suite executes as a CI/CD gate before deploying updated graph prompts or embeddings.",
    ])

    report_md = "\n".join(md_lines)
    if output_md_path:
        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        console.print(f"\n[green]Saved evaluation comparison report to {output_md_path}[/green]")

    return report_md


if __name__ == "__main__":
    generate_comparison_report()
