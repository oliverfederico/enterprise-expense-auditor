"""Unit tests for deterministic math tools."""

from expense_auditor.models.expense import ExpenseCategory, Receipt, ReceiptLineItem
from expense_auditor.tools.math_tools import audit_meals_and_per_diem, audit_lodging_and_incidentals


def test_audit_meal_alcohol_cap():
    # Subtotal $100, Alcohol $40 (40% > 20% cap)
    # Allowed alcohol = $20. Excess = $20.
    r = Receipt(
        receipt_id="REC-01",
        vendor="Bistro",
        date="2026-10-01",
        time="19:30",
        category=ExpenseCategory.MEALS,
        subtotal=100.0,
        total_amount=120.0,
        line_items=[
            ReceiptLineItem(description="Steak", amount=60.0, category=ExpenseCategory.MEALS),
            ReceiptLineItem(description="Cocktails", amount=40.0, category=ExpenseCategory.ALCOHOL, is_alcohol=True),
        ],
    )
    res = audit_meals_and_per_diem([r])
    # Alcohol excess: $20. Eligible meal total: $120 - $20 = $100. Over $75 per diem by $25. Total disallowed: $20 + $25 = $45 (or depending on cap).
    assert len(res["violations"]) >= 1
    rule_ids = [v.rule_id for v in res["violations"]]
    assert "VIO-ALCOHOL-CAP" in rule_ids


def test_audit_meal_solo_breakfast_alcohol():
    # Mimosa during breakfast: 100% disallowed
    r = Receipt(
        receipt_id="REC-02",
        vendor="Morning Diner",
        date="2026-10-01",
        time="08:30",
        category=ExpenseCategory.MEALS,
        subtotal=25.0,
        total_amount=25.0,
        line_items=[
            ReceiptLineItem(description="Pancakes", amount=15.0, category=ExpenseCategory.MEALS),
            ReceiptLineItem(description="Mimosa", amount=10.0, category=ExpenseCategory.ALCOHOL, is_alcohol=True),
        ],
    )
    res = audit_meals_and_per_diem([r])
    rule_ids = [v.rule_id for v in res["violations"]]
    assert "VIO-ALCOHOL-TIMING" in rule_ids
    assert res["total_disallowed"] == 10.0


def test_audit_hotel_tier_caps():
    # Austin hotel rate $250 > $200 tier 2 cap
    r = Receipt(
        receipt_id="REC-03",
        vendor="Austin Hotel",
        date="2026-10-01",
        category=ExpenseCategory.LODGING,
        subtotal=250.0,
        total_amount=280.0,
        line_items=[
            ReceiptLineItem(description="King Room", amount=250.0, category=ExpenseCategory.LODGING),
        ],
    )
    res = audit_lodging_and_incidentals([r], destination="Austin, TX")
    assert len(res["violations"]) == 1
    assert res["violations"][0].rule_id == "VIO-LODGING-CAP"
    assert res["violations"][0].disallowed_amount == 50.0
