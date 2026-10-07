"""Evaluation runner for benchmarking the expense compliance auditor with LangSmith tracing and official evaluators."""

import argparse
import json
import time
from pathlib import Path
from typing import Any
from rich.console import Console
from rich.table import Table
from langsmith import Client
from langsmith.evaluation import evaluate, EvaluationResult
from langsmith.schemas import Example, Run
from expense_auditor.config import settings
from expense_auditor.agent import ExpenseAuditorAgent
from expense_auditor.graph_agent import AdvancedExpenseAuditor
from expense_auditor.models.expense import ExpenseReport
from expense_auditor.models.audit import AuditResult
from evaluation.evaluators.deterministic import (
    evaluate_case_deterministic,
    evaluate_status_accuracy,
    evaluate_disallowed_amount_accuracy,
    evaluate_citation_recall,
)
from evaluation.evaluators.llm_judge import ComplianceLLMJudge

console = Console()
DATASET_NAME = "enterprise-expense-compliance-eval"


def ensure_langsmith_dataset(dataset_path: Path, client: Client) -> str:
    """Ensures the evaluation dataset is uploaded to LangSmith."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    if client.has_dataset(dataset_name=DATASET_NAME):
        ds = client.read_dataset(dataset_name=DATASET_NAME)
        return str(ds.id)

    ds = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Enterprise Expense Policy Compliance Benchmark (25 Cases across 5 slices)",
    )
    for tc in cases:
        client.create_example(
            inputs={"report": tc["report"]},
            outputs={"expected": tc["expected"]},
            dataset_id=ds.id,
            metadata={
                "case_id": tc["case_id"],
                "slice": tc["slice"],
                "description": tc["description"],
            },
        )
    console.print(f"[bold green]✓ Created LangSmith dataset '{DATASET_NAME}' with {len(cases)} examples[/bold green]")
    return str(ds.id)


def run_langsmith_evaluation(
    agent: Any,
    client: Client,
    dataset_name: str = DATASET_NAME,
    experiment_prefix: str = "expense-auditor-eval",
    max_concurrency: int = 2,
) -> Any:
    """Executes the official LangSmith evaluate() runner with deterministic and LLM Judge evaluators."""
    judge = ComplianceLLMJudge()
    judge_cache: dict[str, Any] = {}

    def target(inputs: dict) -> dict:
        rep = ExpenseReport.model_validate(inputs["report"])
        res = agent.audit(rep)
        return res.model_dump()

    def _get_judge_eval(run: Run, example: Example) -> Any:
        rid = str(run.id)
        if rid not in judge_cache:
            tc = {
                "case_id": example.metadata.get("case_id", "TC"),
                "slice": example.metadata.get("slice", "general"),
                "description": example.metadata.get("description", ""),
                "expected": example.outputs["expected"],
            }
            audit_res = AuditResult.model_validate(run.outputs)
            judge_cache[rid] = judge.evaluate(audit_res, tc)
        return judge_cache[rid]

    # Evaluator 1: Status Accuracy
    def status_accuracy(run: Run, example: Example) -> EvaluationResult:
        expected_status = example.outputs["expected"]["status"]
        predicted_status = run.outputs["status"]
        passed = (predicted_status == expected_status)
        return EvaluationResult(
            key="status_accuracy",
            score=1.0 if passed else 0.0,
            comment=f"Predicted: {predicted_status} | Expected: {expected_status}",
        )

    # Evaluator 2: Disallowed Amount Accuracy
    def disallowed_amount_accuracy(run: Run, example: Example) -> EvaluationResult:
        expected_amt = example.outputs["expected"]["expected_disallowed_amount"]
        predicted_amt = run.outputs["disallowed_amount"]
        eval_res = evaluate_disallowed_amount_accuracy(predicted_amt, expected_amt)
        return EvaluationResult(
            key="disallowed_amount_accuracy",
            score=1.0 if eval_res["is_accurate"] else 0.0,
            comment=f"Pred: ${predicted_amt:.2f} | Exp: ${expected_amt:.2f} | Err: ${eval_res['absolute_error']:.2f}",
        )

    # Evaluator 3: Policy Citation Recall
    def policy_citation_recall(run: Run, example: Example) -> EvaluationResult:
        expected_sections = example.outputs["expected"]["expected_policy_sections"]
        audit_res = AuditResult.model_validate(run.outputs)
        eval_res = evaluate_citation_recall(audit_res, expected_sections)
        return EvaluationResult(
            key="citation_recall",
            score=eval_res["recall"],
            comment=f"Recall: {eval_res['recall']*100:.0f}% | Matched: {eval_res.get('matched_sections', [])}",
        )

    # Evaluator 4: LLM Judge Policy Groundedness
    def llm_judge_groundedness(run: Run, example: Example) -> EvaluationResult:
        jr = _get_judge_eval(run, example)
        return EvaluationResult(
            key="llm_judge_groundedness",
            score=jr.policy_groundedness_score / 5.0,
            comment=f"Rating: {jr.policy_groundedness_score}/5 | Critique: {jr.judge_critique}",
        )

    # Evaluator 5: LLM Judge Remediation Actionability
    def llm_judge_actionability(run: Run, example: Example) -> EvaluationResult:
        jr = _get_judge_eval(run, example)
        return EvaluationResult(
            key="llm_judge_actionability",
            score=jr.remediation_actionability_score / 5.0,
            comment=f"Rating: {jr.remediation_actionability_score}/5 | Critique: {jr.judge_critique}",
        )

    # Evaluator 6: LLM Judge Qualitative Agreement
    def llm_judge_agreement(run: Run, example: Example) -> EvaluationResult:
        jr = _get_judge_eval(run, example)
        return EvaluationResult(
            key="llm_judge_agreement",
            score=1.0 if jr.judgment_agreement else 0.0,
            comment=f"Agreed: {jr.judgment_agreement} | Critique: {jr.judge_critique}",
        )

    evaluators = [
        status_accuracy,
        disallowed_amount_accuracy,
        policy_citation_recall,
        llm_judge_groundedness,
        llm_judge_actionability,
        llm_judge_agreement,
    ]

    console.print(f"[bold cyan]Launching LangSmith Experiment with {len(evaluators)} evaluators on dataset '{dataset_name}'...[/bold cyan]")

    experiment_results = evaluate(
        target,
        data=dataset_name,
        evaluators=evaluators,
        experiment_prefix=experiment_prefix,
        client=client,
        max_concurrency=max_concurrency,
        metadata={
            "agent_type": "AdvancedExpenseAuditor" if isinstance(agent, AdvancedExpenseAuditor) else "ExpenseAuditorAgent",
            "model": settings.gemini_model,
        },
    )

    console.print(f"\n[bold green]✓ LangSmith Evaluation Complete![/bold green]")
    console.print(f"Results registered under LangSmith Evaluators tab.")
    return experiment_results


def run_benchmark(
    dataset_path: Path,
    output_path: Path | None = None,
    run_judge: bool = True,
    agent_instance: Any = None,
    sync_langsmith: bool = False,
) -> dict:
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    agent = agent_instance or AdvancedExpenseAuditor()
    judge = ComplianceLLMJudge() if run_judge else None
    engine_name = "advanced-langgraph" if isinstance(agent, AdvancedExpenseAuditor) else "baseline-agent"

    # If LangSmith sync requested and credentials present, run the official LangSmith evaluation experiment
    if sync_langsmith and settings.langchain_tracing_v2 and settings.langchain_api_key:
        try:
            client = Client()
            ensure_langsmith_dataset(dataset_path, client)
            run_langsmith_evaluation(
                agent=agent,
                client=client,
                dataset_name=DATASET_NAME,
                experiment_prefix=f"{engine_name}-eval",
            )
        except Exception as e:
            console.print(f"[yellow]LangSmith experiment evaluation note: {e}[/yellow]")

    console.print(f"\n[bold cyan]Running local benchmark pass on {len(dataset)} test cases...[/bold cyan]\n")

    results_detail = []
    start_time = time.time()

    for idx, tc in enumerate(dataset, 1):
        case_id = tc["case_id"]
        case_slice = tc["slice"]
        desc = tc["description"]
        report = ExpenseReport.model_validate(tc["report"])

        console.print(f"[{idx}/{len(dataset)}] Evaluating {case_id} ({case_slice}): {desc}...", end=" ")

        audit_res = agent.audit(report)
        det_eval = evaluate_case_deterministic(audit_res, tc)

        judge_eval_data = None
        if judge:
            try:
                je = judge.evaluate(audit_res, tc)
                judge_eval_data = je.model_dump()
            except Exception as e:
                console.print(f"[yellow](Judge warning: {e})[/yellow]", end=" ")

        status_icon = "✓" if det_eval["overall_deterministic_pass"] else "✗"
        icon_color = "green" if det_eval["overall_deterministic_pass"] else "red"
        console.print(f"[{icon_color}]{status_icon}[/{icon_color}]")

        record = {
            "case_id": case_id,
            "slice": case_slice,
            "description": desc,
            "deterministic": det_eval,
            "audit_output": audit_res.model_dump(),
            "judge": judge_eval_data,
        }
        results_detail.append(record)

    total_time = round(time.time() - start_time, 2)

    total_cases = len(results_detail)
    status_passes = sum(1 for r in results_detail if r["deterministic"]["status_pass"])
    amount_passes = sum(1 for r in results_detail if r["deterministic"]["amount_pass"])
    overall_passes = sum(1 for r in results_detail if r["deterministic"]["overall_deterministic_pass"])
    avg_recall = sum(r["deterministic"]["citation_recall"] for r in results_detail) / total_cases

    judge_records = [r["judge"] for r in results_detail if r["judge"] is not None]
    avg_groundedness = (
        sum(j["policy_groundedness_score"] for j in judge_records) / len(judge_records)
        if judge_records
        else 0.0
    )
    avg_actionability = (
        sum(j["remediation_actionability_score"] for j in judge_records) / len(judge_records)
        if judge_records
        else 0.0
    )
    judge_agreements = (
        sum(1 for j in judge_records if j["judgment_agreement"]) / len(judge_records)
        if judge_records
        else 0.0
    )

    slices = {}
    for r in results_detail:
        s = r["slice"]
        if s not in slices:
            slices[s] = {"total": 0, "status_pass": 0, "amount_pass": 0, "overall_pass": 0}
        slices[s]["total"] += 1
        if r["deterministic"]["status_pass"]:
            slices[s]["status_pass"] += 1
        if r["deterministic"]["amount_pass"]:
            slices[s]["amount_pass"] += 1
        if r["deterministic"]["overall_deterministic_pass"]:
            slices[s]["overall_pass"] += 1

    summary = {
        "total_cases": total_cases,
        "execution_time_seconds": total_time,
        "metrics": {
            "status_accuracy": round(status_passes / total_cases, 4),
            "disallowed_amount_accuracy": round(amount_passes / total_cases, 4),
            "citation_recall": round(avg_recall, 4),
            "overall_pass_rate": round(overall_passes / total_cases, 4),
            "llm_judge_groundedness_avg": round(avg_groundedness, 2),
            "llm_judge_actionability_avg": round(avg_actionability, 2),
            "llm_judge_agreement_rate": round(judge_agreements, 4),
        },
        "slice_analysis": slices,
        "details": results_detail,
    }

    display_summary(summary)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        console.print(f"\n[green]Saved evaluation results to {output_path}[/green]")

    return summary


def display_summary(summary: dict) -> None:
    console.print("\n" + "=" * 60)
    console.print("[bold green]EVALUATION SUMMARY REPORT[/bold green]")
    console.print("=" * 60)

    m = summary["metrics"]
    metrics_table = Table(title="Overall Performance Metrics", header_style="bold blue")
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Score", justify="right", style="bold yellow")

    metrics_table.add_row("Status Decision Accuracy", f"{m['status_accuracy']*100:.1f}%")
    metrics_table.add_row("Disallowed Amount Accuracy", f"{m['disallowed_amount_accuracy']*100:.1f}%")
    metrics_table.add_row("Policy Citation Recall", f"{m['citation_recall']*100:.1f}%")
    metrics_table.add_row("Overall Deterministic Pass Rate", f"{m['overall_pass_rate']*100:.1f}%")
    metrics_table.add_row("LLM Judge Groundedness (1-5)", f"{m['llm_judge_groundedness_avg']:.2f} / 5.0")
    metrics_table.add_row("LLM Judge Actionability (1-5)", f"{m['llm_judge_actionability_avg']:.2f} / 5.0")
    metrics_table.add_row("LLM Judge Agreement Rate", f"{m['llm_judge_agreement_rate']*100:.1f}%")
    console.print(metrics_table)

    slice_table = Table(title="Performance by Evaluation Slice", header_style="bold magenta")
    slice_table.add_column("Slice Name", style="white")
    slice_table.add_column("Total", justify="right")
    slice_table.add_column("Status Match", justify="right")
    slice_table.add_column("Amount Match", justify="right")
    slice_table.add_column("Full Pass Rate", justify="right", style="bold green")

    for s_name, data in summary["slice_analysis"].items():
        total = data["total"]
        status_pct = (data["status_pass"] / total) * 100
        amount_pct = (data["amount_pass"] / total) * 100
        full_pct = (data["overall_pass"] / total) * 100
        slice_table.add_row(
            s_name,
            str(total),
            f"{status_pct:.1f}%",
            f"{amount_pct:.1f}%",
            f"{full_pct:.1f}%",
        )
    console.print(slice_table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run compliance auditor evaluation.")
    parser.add_argument(
        "--engine",
        choices=["basic", "advanced"],
        default="advanced",
        help="Auditor engine to evaluate: basic or advanced",
    )
    parser.add_argument(
        "--dataset",
        default="evaluation/dataset.json",
        help="Path to evaluation dataset JSON",
    )
    parser.add_argument(
        "--output",
        default="evaluation/results_advanced.json",
        help="Path to save evaluation output",
    )
    parser.add_argument(
        "--langsmith",
        action="store_true",
        help="Run official LangSmith evaluate() experiment logging all evaluators to LangSmith UI",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip LLM Judge evaluation for faster local runs",
    )
    args = parser.parse_args()

    agent = AdvancedExpenseAuditor() if args.engine == "advanced" else ExpenseAuditorAgent()

    # Automatically enable langsmith experiment if credentials are present
    should_sync_langsmith = args.langsmith or bool(settings.langchain_api_key and settings.langchain_tracing_v2)

    run_benchmark(
        dataset_path=Path(args.dataset),
        output_path=Path(args.output),
        run_judge=not args.no_judge,
        agent_instance=agent,
        sync_langsmith=should_sync_langsmith,
    )


if __name__ == "__main__":
    main()
