"""Unit tests for deterministic transit tools."""

from expense_auditor.models.expense import ExpenseCategory, Receipt, ReceiptLineItem
from expense_auditor.tools.transit_tools import audit_ground_transportation


def test_transit_under_15_min_disallowed():
    r = Receipt(
        receipt_id="REC-T1",
        vendor="Uber",
        date="2026-10-01",
        time="14:00",
        category=ExpenseCategory.GROUND_TRANSIT,
        subtotal=25.0,
        total_amount=25.0,
        line_items=[
            ReceiptLineItem(description="UberX", amount=25.0, category=ExpenseCategory.GROUND_TRANSIT),
        ],
    )
    notes = "Subway took 9 minutes but I took Uber."
    res = audit_ground_transportation([r], notes=notes)
    assert len(res["violations"]) == 1
    assert res["violations"][0].rule_id == "VIO-TRANSIT-15MIN"
    assert res["violations"][0].disallowed_amount == 25.0


def test_transit_late_night_exception():
    r = Receipt(
        receipt_id="REC-T2",
        vendor="Uber",
        date="2026-10-01",
        time="23:30",
        category=ExpenseCategory.GROUND_TRANSIT,
        subtotal=25.0,
        total_amount=25.0,
        line_items=[
            ReceiptLineItem(description="UberX Late Night", amount=25.0, category=ExpenseCategory.GROUND_TRANSIT),
        ],
    )
    notes = "Subway took 10 minutes. Late night ride after deployment."
    res = audit_ground_transportation([r], notes=notes)
    assert len(res["violations"]) == 0
    assert res["total_disallowed"] == 0.0


def test_transit_heavy_equipment_exception():
    r = Receipt(
        receipt_id="REC-T3",
        vendor="Lyft",
        date="2026-10-01",
        time="15:00",
        category=ExpenseCategory.GROUND_TRANSIT,
        subtotal=30.0,
        total_amount=30.0,
        line_items=[
            ReceiptLineItem(description="Lyft XL", amount=30.0, category=ExpenseCategory.GROUND_TRANSIT),
        ],
    )
    notes = "Subway was 10 min away, but carried 40 lbs of booth banner stands."
    res = audit_ground_transportation([r], notes=notes)
    assert len(res["violations"]) == 0
    assert res["total_disallowed"] == 0.0
