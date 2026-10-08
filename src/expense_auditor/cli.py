"""Command-line interface for running the Expense Policy Compliance Auditor."""

import argparse
import json
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from expense_auditor.agent import ExpenseAuditorAgent
from expense_auditor.graph_agent import AdvancedExpenseAuditor
from expense_auditor.models.expense import ExpenseReport
from expense_auditor.models.audit import AuditResult, AuditStatus

console = Console()


def display_audit_result(result: AuditResult) -> None:
    """Renders a beautifully formatted audit report to the terminal using rich."""
    status_colors = {
        AuditStatus.APPROVED: "bold green",
        AuditStatus.FLAGGED_FOR_REVIEW: "bold yellow",
        AuditStatus.REJECTED: "bold red",
    }
    color = status_colors.get(result.status, "white")

    # Header Panel
    console.print(
        Panel(
            f"[{color}]STATUS: {result.status.value}[/{color}]\n"
            f"Report ID: {result.report_id}\n"
            f"Total Claimed: ${result.total_claimed:.2f} | "
            f"Approved: ${result.approved_amount:.2f} | "
            f"Disallowed: ${result.disallowed_amount:.2f}",
            title="[bold blue]Enterprise Expense Audit Decision[/bold blue]",
            expand=False,
        )
    )

    # Summary
    console.print(f"\n[bold]Audit Summary:[/bold] {result.audit_summary}\n")

    # Violations Table
    if result.violations:
        table = Table(title="Detected Violations", header_style="bold magenta")
        table.add_column("Rule ID", style="cyan", no_wrap=True)
        table.add_column("Section", style="white")
        table.add_column("Severity", style="bold red")
        table.add_column("Disallowed", justify="right", style="red")
        table.add_column("Evidence", style="dim")

        for v in result.violations:
            table.add_row(
                v.rule_id,
                v.policy_section,
                v.severity.value,
                f"${v.disallowed_amount:.2f}",
                v.evidence,
            )
        console.print(table)
    else:
        console.print("[green]✓ No policy violations identified.[/green]\n")

    # Remediation
    if result.remediation_steps:
        console.print("[bold yellow]Required Remediation Actions for Employee:[/bold yellow]")
        for idx, step in enumerate(result.remediation_steps, 1):
            console.print(f"  {idx}. {step}")
        console.print("")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit corporate expense reports against T&E policies.")
    parser.add_argument("report_file", nargs="?", help="Path to JSON expense report file")
    parser.add_argument(
        "--engine",
        choices=["basic", "advanced"],
        default="advanced",
        help="Auditor engine to use: basic (initial RAG agent) or advanced (LangGraph StateGraph with deterministic tools)",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of rich table")
    args = parser.parse_args()

    if not args.report_file:
        console.print("[yellow]No report file provided. Use: expense-auditor <path-to-report.json>[/yellow]")
        sys.exit(1)

    path = Path(args.report_file)
    if not path.exists():
        console.print(f"[red]Error: file not found: {path}[/red]")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    report = ExpenseReport.model_validate(data)
    agent = AdvancedExpenseAuditor() if args.engine == "advanced" else ExpenseAuditorAgent()
    result = agent.audit(report)

    if args.json:
        print(json.dumps(result.model_dump(), indent=2))
    else:
        display_audit_result(result)


if __name__ == "__main__":
    main()
