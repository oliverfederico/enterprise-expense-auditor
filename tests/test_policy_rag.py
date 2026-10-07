"""Unit tests for corporate policy store and RAG retriever."""

from pathlib import Path
from expense_auditor.models.expense import ExpenseCategory, ExpenseReport, Receipt
from expense_auditor.rag.policy_store import PolicyStore
from expense_auditor.rag.retriever import PolicyRetriever


def test_policy_store_loading():
    policy_path = Path("docs/policy_document.md")
    store = PolicyStore(policy_path)
    sections = store.get_all_sections()
    assert len(sections) >= 8

    sec_per_diem = store.get_section_by_id("SEC-1.1")
    assert sec_per_diem is not None
    assert "75.00" in sec_per_diem.content

    sec_alcohol = store.get_section_by_id("SEC-1.2")
    assert sec_alcohol is not None
    assert "20%" in sec_alcohol.content

    sec_transit = store.get_section_by_id("SEC-2.1")
    assert sec_transit is not None
    assert "15 minutes" in sec_transit.content


def test_policy_retriever_for_meal_report():
    retriever = PolicyRetriever()
    report = ExpenseReport(
        report_id="EXP-101",
        employee_id="EMP-01",
        employee_name="Bob",
        submission_date="2026-10-02",
        trip_purpose="Team Offsite",
        receipts=[
            Receipt(
                receipt_id="REC-01",
                vendor="Steakhouse",
                date="2026-10-01",
                category=ExpenseCategory.MEALS,
                subtotal=80.0,
                total_amount=95.0,
            )
        ],
    )
    retrieved = retriever.retrieve_for_report(report)
    section_ids = [s.section_id for s in retrieved]
    assert "SEC-1.1" in section_ids  # Per diem rule
    assert "SEC-1.3" in section_ids  # Itemized receipt rule


def test_policy_retriever_for_rideshare_report():
    retriever = PolicyRetriever()
    report = ExpenseReport(
        report_id="EXP-102",
        employee_id="EMP-02",
        employee_name="Carol",
        submission_date="2026-10-02",
        trip_purpose="Client Visit",
        origin="Downtown Hotel",
        destination="Client HQ",
        justification_notes="Took Uber ride because it was raining.",
        receipts=[
            Receipt(
                receipt_id="REC-02",
                vendor="Uber",
                date="2026-10-01",
                category=ExpenseCategory.GROUND_TRANSIT,
                subtotal=24.0,
                total_amount=24.0,
            )
        ],
    )
    retrieved = retriever.retrieve_for_report(report)
    section_ids = [s.section_id for s in retrieved]
    assert "SEC-2.1" in section_ids  # Transit vs Rideshare rule
    assert "SEC-2.2" in section_ids  # Transit Exceptions rule
