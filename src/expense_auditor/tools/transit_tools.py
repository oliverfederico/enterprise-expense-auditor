"""Deterministic auditing tools for ground transit and rideshares."""

import re
from datetime import datetime
from typing import Any
from expense_auditor.models.expense import ExpenseCategory, Receipt
from expense_auditor.models.audit import Violation, ViolationSeverity


def audit_ground_transportation(
    receipts: list[Receipt],
    notes: str = "",
    origin: str | None = None,
    destination: str | None = None,
) -> dict[str, Any]:
    """Deterministically audits rideshares (Uber, Lyft, Taxi) against SEC-2.1 and SEC-2.2."""
    violations: list[Violation] = []
    combined_notes = (notes or "").lower()

    for r in receipts:
        if r.category != ExpenseCategory.GROUND_TRANSIT:
            continue

        vendor_lower = r.vendor.lower()
        is_rideshare = any(v in vendor_lower for v in ["uber", "lyft", "taxi", "cab"])
        if not is_rideshare:
            continue

        # Check for documented public transit duration in notes
        # e.g., "subway takes 9 minutes", "14 minute train ride", "35 minutes"
        transit_duration = None
        duration_matches = re.findall(r"(\d+)\s*(?:min|minute)", combined_notes)
        if duration_matches:
            # take the first matched duration
            transit_duration = int(duration_matches[0])

        # Check late night exception (SEC-2.2): 22:00 to 06:00
        is_late_night = False
        if r.time:
            try:
                t = datetime.strptime(r.time, "%H:%M").time()
                if t.hour >= 22 or t.hour < 6:
                    is_late_night = True
            except ValueError:
                pass
        if "late night" in combined_notes or "past 11" in combined_notes or "23:" in combined_notes:
            is_late_night = True

        # Check heavy equipment exception (SEC-2.2): >30 lbs
        has_heavy_equipment = False
        equip_match = re.search(r"(\d+)\s*(?:lbs?|pounds)", combined_notes)
        if equip_match:
            lbs = int(equip_match.group(1))
            if lbs >= 30:
                has_heavy_equipment = True
        if "booth" in combined_notes and "equipment" in combined_notes and has_heavy_equipment:
            has_heavy_equipment = True

        # Check severe emergency / outage (SEC-2.2)
        has_transit_outage = "transit outage" in combined_notes or "blizzard warning" in combined_notes

        # Ordinary rain or tired excuses are explicitly invalid
        is_exempt = is_late_night or has_heavy_equipment or has_transit_outage

        # Decision rule: if transit duration is documented and < 15 minutes, rideshare is disallowed unless exempt
        if transit_duration is not None and transit_duration < 15 and not is_exempt:
            violations.append(
                Violation(
                    rule_id="VIO-TRANSIT-15MIN",
                    policy_section="SEC-2.1: Public Transit Preference & Rideshare Limitation",
                    severity=ViolationSeverity.HARD_VIOLATION,
                    description=f"Rideshare utilized when public transit was under 15 minutes ({transit_duration} min) without an approved exception.",
                    evidence=f"Public transit duration documented as {transit_duration} min; fare of ${r.total_amount:.2f} is non-reimbursable.",
                    disallowed_amount=round(r.total_amount, 2),
                )
            )

    total_disallowed = round(sum(v.disallowed_amount for v in violations), 2)
    return {
        "violations": violations,
        "total_disallowed": total_disallowed,
    }
