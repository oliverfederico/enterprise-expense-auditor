"""Deterministic mathematical auditing tools for meals, per diem, and lodging."""

from datetime import datetime
from typing import Any
from expense_auditor.models.expense import ExpenseCategory, Receipt
from expense_auditor.models.audit import Violation, ViolationSeverity

TIER_1_CITIES = {
    "new york", "nyc", "manhattan", "san francisco", "sf",
    "london", "tokyo", "washington dc", "dc", "washington, dc",
    "district of columbia", "the willard",
}


def audit_meals_and_per_diem(receipts: list[Receipt]) -> dict[str, Any]:
    """Deterministically audits meals for alcohol caps and daily per diem limits.

    Follows corporate accounting sequence:
    1. For each individual travel meal receipt (MEALS category):
       - Check if alcohol consumed at breakfast or lunch (100% disallowed).
       - For dinners, check if alcohol charges exceed 20% of meal subtotal.
       - Disallow any excess alcohol expenditure.
    2. Group remaining eligible individual meal spend by calendar date.
    3. Cap total daily eligible individual meal spend at $75.00/day.
    Note: Client entertainment is audited separately under SEC-3.2 ($150/attendee).
    """
    violations: list[Violation] = []

    # 1. Detect artificial receipt splitting (SEC-5.1)
    by_date_vendor: dict[tuple[str, str], list[Receipt]] = {}
    for r in receipts:
        if r.category == ExpenseCategory.MEALS:
            by_date_vendor.setdefault((r.date, r.vendor.lower()), []).append(r)

    for (d_str, vendor), r_list in by_date_vendor.items():
        if len(r_list) > 1:
            split_total = sum(r.total_amount for r in r_list)
            violations.append(
                Violation(
                    rule_id="VIO-RECEIPT-SPLITTING",
                    policy_section="SEC-5.1: Artificial Receipt Splitting",
                    severity=ViolationSeverity.HARD_VIOLATION,
                    description="Multiple meal receipts on the same date from the same vendor indicating artificial splitting.",
                    evidence=f"{len(r_list)} receipts from {r_list[0].vendor} on {d_str} totaling ${split_total:.2f}.",
                    disallowed_amount=0.0,
                )
            )

    # Group individual meals by date
    by_date: dict[str, list[Receipt]] = {}
    for r in receipts:
        # Only individual travel meals are audited under SEC-1.1 per diem!
        if r.category == ExpenseCategory.MEALS:
            by_date.setdefault(r.date, []).append(r)

    daily_spend_details: dict[str, float] = {}

    for d_str, date_receipts in by_date.items():
        date_eligible_meal_spend = 0.0

        for r in date_receipts:
            alcohol_items = [item for item in r.line_items if item.is_alcohol]
            alcohol_total = sum(item.amount for item in alcohol_items)

            # Determine meal time / type
            is_breakfast = False
            is_lunch = False
            if r.time:
                try:
                    t = datetime.strptime(r.time, "%H:%M").time()
                    if t.hour < 11:
                        is_breakfast = True
                    elif 11 <= t.hour < 16:
                        is_lunch = True
                except ValueError:
                    pass

            # Rule SEC-1.2: Alcohol timing & cap
            receipt_alcohol_disallowed = 0.0
            if alcohol_total > 0:
                if is_breakfast or is_lunch:
                    receipt_alcohol_disallowed = alcohol_total
                    violations.append(
                        Violation(
                            rule_id="VIO-ALCOHOL-TIMING",
                            policy_section="SEC-1.2: Alcohol Policy",
                            severity=ViolationSeverity.HARD_VIOLATION,
                            description=f"Alcohol consumed during {'breakfast' if is_breakfast else 'lunch'} is 100% non-reimbursable.",
                            evidence=f"${alcohol_total:.2f} alcohol claimed on {r.vendor} receipt at {r.time or 'daytime'}.",
                            disallowed_amount=round(receipt_alcohol_disallowed, 2),
                        )
                    )
                else:
                    # Dinner cap: max 20% of subtotal
                    max_allowed_alcohol = round(r.subtotal * 0.20, 2)
                    if alcohol_total > max_allowed_alcohol:
                        overage = alcohol_total - max_allowed_alcohol
                        receipt_alcohol_disallowed = overage
                        ratio = (alcohol_total / r.subtotal) if r.subtotal > 0 else 1.0
                        violations.append(
                            Violation(
                                rule_id="VIO-ALCOHOL-CAP",
                                policy_section="SEC-1.2: Alcohol Policy",
                                severity=ViolationSeverity.HARD_VIOLATION,
                                description=f"Alcohol exceeded 20% of meal subtotal ({ratio*100:.1f}%).",
                                evidence=f"${alcohol_total:.2f} alcohol on ${r.subtotal:.2f} subtotal (20% cap is ${max_allowed_alcohol:.2f}, excess is ${overage:.2f}).",
                                disallowed_amount=round(overage, 2),
                            )
                        )

            # Remaining eligible spend on this receipt
            date_eligible_meal_spend += max(0.0, r.total_amount - receipt_alcohol_disallowed)

        # Step 2: Evaluate daily $75 per diem
        per_diem_cap = 75.00
        daily_spend_details[d_str] = round(date_eligible_meal_spend, 2)

        if date_eligible_meal_spend > per_diem_cap:
            per_diem_excess = round(date_eligible_meal_spend - per_diem_cap, 2)
            violations.append(
                Violation(
                    rule_id="VIO-DAILY-PERDIEM",
                    policy_section="SEC-1.1: Daily Per Diem Limit",
                    severity=ViolationSeverity.HARD_VIOLATION,
                    description=f"Total meals on {d_str} exceeded the $75.00 daily per diem limit.",
                    evidence=f"Cumulative eligible meals on {d_str} reached ${date_eligible_meal_spend:.2f}, exceeding $75.00 cap by ${per_diem_excess:.2f}.",
                    disallowed_amount=per_diem_excess,
                )
            )

    total_disallowed = round(sum(v.disallowed_amount for v in violations), 2)
    return {
        "violations": violations,
        "total_disallowed": total_disallowed,
        "daily_spend": daily_spend_details,
    }


def audit_lodging_and_incidentals(
    receipts: list[Receipt],
    destination: str | None = None,
    origin: str | None = None,
    trip_purpose: str | None = None,
) -> dict[str, Any]:
    """Deterministically audits hotel lodging rates and non-reimbursable incidentals."""
    violations: list[Violation] = []

    search_context = f"{destination or ''} {origin or ''} {trip_purpose or ''}".lower()
    is_tier_1_context = any(city in search_context for city in TIER_1_CITIES)

    for r in receipts:
        if r.category == ExpenseCategory.LODGING:
            receipt_text = (r.vendor + " " + " ".join(item.description for item in r.line_items)).lower()
            is_tier_1 = is_tier_1_context or any(city in receipt_text for city in TIER_1_CITIES)
            effective_cap = 300.00 if is_tier_1 else 200.00

            # Find room rate item
            room_items = [
                item for item in r.line_items if item.category == ExpenseCategory.LODGING
            ]
            room_cost = sum(item.amount for item in room_items) if room_items else r.subtotal

            if room_cost > effective_cap:
                room_excess = round(room_cost - effective_cap, 2)
                violations.append(
                    Violation(
                        rule_id="VIO-LODGING-CAP",
                        policy_section="SEC-4.1: Lodging Rate Limits",
                        severity=ViolationSeverity.HARD_VIOLATION,
                        description=f"Nightly hotel room rate exceeded the ${effective_cap:.2f} cap for this market.",
                        evidence=f"Room rate was ${room_cost:.2f} vs allowable ${effective_cap:.2f} cap.",
                        disallowed_amount=room_excess,
                    )
                )

            # Check for non-reimbursable incidentals (minibar, movies, spa)
            for item in r.line_items:
                desc = item.description.lower()
                if item.category == ExpenseCategory.INCIDENTAL or "minibar" in desc or "movie" in desc or "spa" in desc:
                    violations.append(
                        Violation(
                            rule_id="VIO-HOTEL-INCIDENTAL",
                            policy_section="SEC-4.2: Non-Reimbursable Personal Incidentals",
                            severity=ViolationSeverity.HARD_VIOLATION,
                            description="Personal hotel incidentals are strictly non-reimbursable.",
                            evidence=f"Personal charge: {item.description} (${item.amount:.2f}).",
                            disallowed_amount=round(item.amount, 2),
                        )
                    )

    total_disallowed = round(sum(v.disallowed_amount for v in violations), 2)
    return {
        "violations": violations,
        "total_disallowed": total_disallowed,
    }
