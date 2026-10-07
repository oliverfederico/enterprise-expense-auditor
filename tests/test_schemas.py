"""Unit tests for Pydantic domain models."""

from expense_auditor.models.expense import (
    ExpenseCategory,
    ExpenseReport,
    Receipt,
    ReceiptLineItem,
)
from expense_auditor.models.audit import AuditResult, AuditStatus, Violation, ViolationSeverity


def test_receipt_subtotal_calculation():
    # If subtotal is 0 and total is provided, subtotal auto-calculates
    r = Receipt(
        receipt_id="REC-001",
        vendor="Test Bistro",
        date="2026-10-01",
        category=ExpenseCategory.MEALS,
        subtotal=0.0,
        tax=5.0,
        tip=10.0,
        total_amount=65.0,
    )
    assert r.subtotal == 50.0
    assert r.total_amount == 65.0


def test_expense_report_total_claimed():
    r1 = Receipt(
        receipt_id="REC-001",
        vendor="Cafe A",
        date="2026-10-01",
        category=ExpenseCategory.MEALS,
        subtotal=20.0,
        total_amount=20.0,
    )
    r2 = Receipt(
        receipt_id="REC-002",
        vendor="Bistro B",
        date="2026-10-01",
        category=ExpenseCategory.MEALS,
        subtotal=45.0,
        total_amount=45.0,
    )
    report = ExpenseReport(
        report_id="EXP-101",
        employee_id="EMP-01",
        employee_name="Alice Smith",
        submission_date="2026-10-02",
        trip_purpose="Client Sales Pitch",
        receipts=[r1, r2],
    )
    assert report.total_claimed == 65.00


def test_audit_result_serialization():
    violation = Violation(
        rule_id="VIO-ALCOHOL-CAP",
        policy_section="SEC-1.2: Alcohol Policy",
        severity=ViolationSeverity.HARD_VIOLATION,
        description="Alcohol exceeds 20% limit",
        evidence="$30 alcohol on $60 food",
        disallowed_amount=18.0,
    )
    audit = AuditResult(
        report_id="EXP-101",
        status=AuditStatus.FLAGGED_FOR_REVIEW,
        total_claimed=100.0,
        approved_amount=82.0,
        disallowed_amount=18.0,
        violations=[violation],
        remediation_steps=["Please provide itemized bill."],
        audit_summary="Alcohol overage disallowed.",
    )
    data = audit.model_dump()
    assert data["status"] == "FLAGGED_FOR_REVIEW"
    assert data["disallowed_amount"] == 18.0
    assert len(data["violations"]) == 1
