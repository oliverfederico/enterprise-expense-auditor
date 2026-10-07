"""Deterministic programmatic evaluators for expense compliance audits."""

from typing import Any
from expense_auditor.models.audit import AuditResult, AuditStatus


def evaluate_status_accuracy(predicted_status: AuditStatus, expected_status: str) -> bool:
    """Exact match check on audit status."""
    return predicted_status.value == expected_status


def evaluate_disallowed_amount_accuracy(
    predicted_disallowed: float, expected_disallowed: float, tolerance: float = 1.00
) -> dict[str, Any]:
    """Evaluates whether the disallowed amount matches ground truth within tolerance."""
    abs_diff = abs(predicted_disallowed - expected_disallowed)
    is_accurate = abs_diff <= tolerance
    return {
        "is_accurate": is_accurate,
        "absolute_error": round(abs_diff, 2),
        "predicted": predicted_disallowed,
        "expected": expected_disallowed,
    }


def evaluate_citation_recall(
    result: AuditResult, expected_sections: list[str]
) -> dict[str, Any]:
    """Calculates recall of expected policy sections cited in violations or citations."""
    if not expected_sections:
        return {"recall": 1.0, "missing_sections": [], "matched_sections": []}

    cited_texts = set()
    for v in result.violations:
        cited_texts.add(v.rule_id)
        cited_texts.add(v.policy_section)
    for c in result.citations:
        cited_texts.add(c.section_id)
        cited_texts.add(c.title)

    cited_blob = " ".join(cited_texts).upper()

    matched = []
    missing = []
    for sec in expected_sections:
        if sec.upper() in cited_blob:
            matched.append(sec)
        else:
            missing.append(sec)

    recall = len(matched) / len(expected_sections) if expected_sections else 1.0
    return {
        "recall": round(recall, 2),
        "matched_sections": matched,
        "missing_sections": missing,
    }


def evaluate_case_deterministic(result: AuditResult, test_case: dict[str, Any]) -> dict[str, Any]:
    """Runs all deterministic evaluations against a single test case result."""
    expected = test_case["expected"]

    status_pass = evaluate_status_accuracy(result.status, expected["status"])
    amount_eval = evaluate_disallowed_amount_accuracy(
        result.disallowed_amount, expected["expected_disallowed_amount"]
    )
    citation_eval = evaluate_citation_recall(result, expected["expected_policy_sections"])

    all_passed = status_pass and amount_eval["is_accurate"] and (citation_eval["recall"] >= 0.8)

    return {
        "case_id": test_case["case_id"],
        "slice": test_case["slice"],
        "status_pass": status_pass,
        "predicted_status": result.status.value,
        "expected_status": expected["status"],
        "amount_pass": amount_eval["is_accurate"],
        "disallowed_error": amount_eval["absolute_error"],
        "predicted_disallowed": result.disallowed_amount,
        "expected_disallowed": expected["expected_disallowed_amount"],
        "citation_recall": citation_eval["recall"],
        "missing_citations": citation_eval["missing_sections"],
        "overall_deterministic_pass": all_passed,
    }
