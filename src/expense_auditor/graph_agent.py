"""Advanced compliance auditor built with LangGraph StateGraph and deterministic auditing tools."""

import re
from typing import Any, TypedDict
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from expense_auditor.config import settings
from expense_auditor.models.expense import ExpenseCategory, ExpenseReport
from expense_auditor.models.policy import PolicyCitation, PolicySection
from expense_auditor.models.audit import AuditResult, AuditStatus, Violation, ViolationSeverity
from expense_auditor.rag.retriever import PolicyRetriever
from expense_auditor.tools.math_tools import (
    audit_meals_and_per_diem,
    audit_lodging_and_incidentals,
)
from expense_auditor.tools.transit_tools import audit_ground_transportation


QUALITATIVE_SYSTEM_PROMPT = """You are a Senior Corporate Expense Compliance Auditor.
You review employee expense reports alongside deterministic calculation results produced by automated audit tools.

### POLICY CLAUSES:
{policy_context}

### DETERMINISTIC TOOL FINDINGS ALREADY VERIFIED:
- Deterministic Violations: {deterministic_violations_summary}
- Deterministic Disallowed Total: ${deterministic_disallowed:.2f}

### YOUR RESPONSIBILITIES:
1. Review qualitative and documentation compliance:
   - Client Entertainment (SEC-3.1): Are full names, titles, and company affiliations documented for all attendees? Is the business justification substantive and specific? If missing attendee names or vague justification, flag with status FLAGGED_FOR_REVIEW and severity MISSING_INFO.
   - Client Entertainment Spending Cap (SEC-3.2): Maximum $150.00 per attendee.
   - Itemized Receipts (SEC-1.3): Are itemized receipts supplied for all meal expenses > $25? If non-itemized receipt for > $25, flag with severity MISSING_INFO. (If <= $25, itemization is NOT required).
   - Rideshare Exceptions (SEC-2.2): Late-night (22:00-06:00) or heavy equipment (>30 lbs) are approved exceptions.
2. Status Guidance:
   - If ANY HARD_VIOLATION exists (math overages, unauthorized rideshare, unapproved lodging rates): Status is REJECTED.
   - If NO hard violations, but missing attendee names, vague justification, or missing itemized receipt > $25: Status is FLAGGED_FOR_REVIEW.
   - If fully compliant with all policies: Status is APPROVED.
3. For FLAGGED_FOR_REVIEW cases, do NOT disallow money; hold for clarification ($0.00 disallowed).
4. Provide courteous remediation instructions and a clear summary.
"""


QUALITATIVE_USER_PROMPT = """Please evaluate this report:

REPORT METADATA:
- Report ID: {report_id}
- Employee: {employee_name} ({employee_id})
- Department: {department}
- Submission Date: {submission_date}
- Trip Purpose: {trip_purpose}
- Route: {origin} -> {destination}
- Justification Notes: {justification_notes}
- Documented Attendees: {attendees}

RECEIPTS:
{receipts_detail}
"""


class AuditorGraphState(TypedDict):
    report: ExpenseReport
    policy_sections: list[PolicySection]
    policy_context: str
    deterministic_violations: list[Violation]
    deterministic_disallowed: float
    qualitative_result: dict[str, Any]
    final_result: AuditResult


def create_expense_auditor_graph(
    model_name: str | None = None,
    retriever: PolicyRetriever | None = None,
):
    model = model_name or settings.gemini_model
    policy_retriever = retriever or PolicyRetriever()
    llm = ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.google_api_key,
        temperature=0.0,
    )

    def node_retrieve(state: AuditorGraphState) -> dict:
        report = state["report"]
        sections = policy_retriever.retrieve_for_report(report)
        context = policy_retriever.format_policies_for_prompt(sections)
        return {"policy_sections": sections, "policy_context": context}

    def node_deterministic_audit(state: AuditorGraphState) -> dict:
        report = state["report"]
        violations: list[Violation] = []

        # 1. Meals & Per Diem
        meal_res = audit_meals_and_per_diem(report.receipts)
        violations.extend(meal_res["violations"])

        # 2. Lodging & Incidentals
        lodging_res = audit_lodging_and_incidentals(
            report.receipts,
            destination=report.destination,
            origin=report.origin,
            trip_purpose=report.trip_purpose,
        )
        violations.extend(lodging_res["violations"])

        # 3. Ground Transportation
        transit_res = audit_ground_transportation(
            report.receipts,
            notes=report.justification_notes,
            origin=report.origin,
            destination=report.destination,
        )
        violations.extend(transit_res["violations"])

        # 4. Client Entertainment Per-Person Cap (SEC-3.2: $150/person)
        if any(r.category == ExpenseCategory.CLIENT_ENTERTAINMENT for r in report.receipts):
            attendee_count = len(report.attendees)
            if attendee_count > 0:
                client_claimed = sum(
                    r.total_amount for r in report.receipts if r.category == ExpenseCategory.CLIENT_ENTERTAINMENT
                )
                max_allowed = attendee_count * 150.00
                if client_claimed > max_allowed:
                    cap_excess = round(client_claimed - max_allowed, 2)
                    violations.append(
                        Violation(
                            rule_id="VIO-CLIENT-PER-PERSON-CAP",
                            policy_section="SEC-3.2: Per-Person Spending Cap",
                            severity=ViolationSeverity.HARD_VIOLATION,
                            description=f"Client entertainment exceeded the $150.00 per-person limit ({attendee_count} attendees).",
                            evidence=f"Claimed ${client_claimed:.2f} for {attendee_count} attendees (max allowed is ${max_allowed:.2f}, excess is ${cap_excess:.2f}).",
                            disallowed_amount=cap_excess,
                        )
                    )

        total_disallowed = round(sum(v.disallowed_amount for v in violations), 2)
        return {
            "deterministic_violations": violations,
            "deterministic_disallowed": total_disallowed,
        }

    def node_qualitative_audit(state: AuditorGraphState) -> dict:
        report = state["report"]
        det_violations = state["deterministic_violations"]
        det_disallowed = state["deterministic_disallowed"]

        lines = []
        for idx, r in enumerate(report.receipts, 1):
            time_str = f" at {r.time}" if r.time else ""
            lines.append(
                f"Receipt #{idx} [{r.receipt_id}]: {r.vendor} on {r.date}{time_str} | Category: {r.category.value} | Total: ${r.total_amount:.2f}"
            )
            lines.append(f"  Itemized: {'Yes' if r.is_itemized else 'No (Summary slip only)'}")
            if r.line_items:
                for it in r.line_items:
                    lines.append(f"    - {it.description}: ${it.amount:.2f} {'[ALCOHOL]' if it.is_alcohol else ''}")
            elif r.raw_text:
                lines.append(f"    Raw Text: {r.raw_text}")
        receipts_detail = "\n".join(lines)

        det_summary = "\n".join(
            f"- {v.rule_id} ({v.policy_section}): {v.description} [Disallowed: ${v.disallowed_amount:.2f}]"
            for v in det_violations
        ) or "None (All deterministic mathematical checks passed)"

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", QUALITATIVE_SYSTEM_PROMPT),
                ("user", QUALITATIVE_USER_PROMPT),
            ]
        )

        messages = prompt.format_messages(
            policy_context=state["policy_context"],
            deterministic_violations_summary=det_summary,
            deterministic_disallowed=det_disallowed,
            report_id=report.report_id,
            employee_name=report.employee_name,
            employee_id=report.employee_id,
            department=report.department or "N/A",
            submission_date=report.submission_date,
            trip_purpose=report.trip_purpose,
            origin=report.origin or "N/A",
            destination=report.destination or "N/A",
            justification_notes=report.justification_notes or "None provided",
            attendees=", ".join(report.attendees) if report.attendees else "None listed",
            receipts_detail=receipts_detail,
        )

        structured_llm = llm.with_structured_output(AuditResult)
        result = structured_llm.invoke(messages)
        return {"qualitative_result": result.model_dump()}

    def node_synthesize(state: AuditorGraphState) -> dict:
        report = state["report"]
        det_violations = state["deterministic_violations"]
        qual_res_dict = state["qualitative_result"]

        qual_violations_raw = qual_res_dict.get("violations", [])
        qual_violations: list[Violation] = []
        for v in qual_violations_raw:
            if isinstance(v, dict):
                qual_violations.append(Violation.model_validate(v))
            elif isinstance(v, Violation):
                qual_violations.append(v)

        seen_rules = set()
        merged_violations: list[Violation] = []

        # Deterministic violations take absolute precedence
        for v in det_violations:
            seen_rules.add(v.rule_id)
            merged_violations.append(v)

        for v in qual_violations:
            # Avoid duplicate rules or double penalty
            if v.rule_id not in seen_rules and not any(v.rule_id[:5] == r[:5] for r in seen_rules):
                seen_rules.add(v.rule_id)
                merged_violations.append(v)

        has_hard = any(v.severity == ViolationSeverity.HARD_VIOLATION for v in merged_violations)
        has_missing_info = any(v.severity == ViolationSeverity.MISSING_INFO for v in merged_violations)
        is_qual_flagged = qual_res_dict.get("status") == "FLAGGED_FOR_REVIEW"

        if has_hard:
            final_status = AuditStatus.REJECTED
            final_disallowed = round(sum(v.disallowed_amount for v in merged_violations), 2)
        elif has_missing_info or is_qual_flagged:
            final_status = AuditStatus.FLAGGED_FOR_REVIEW
            # Missing info cases hold for review, zero disallowed initially
            final_disallowed = 0.0
            for v in merged_violations:
                if v.severity == ViolationSeverity.MISSING_INFO:
                    v.disallowed_amount = 0.0
        else:
            final_status = AuditStatus.APPROVED
            final_disallowed = 0.0

        total_claimed = report.total_claimed
        approved_amount = round(max(0.0, total_claimed - final_disallowed), 2)

        remediation_steps = qual_res_dict.get("remediation_steps", [])
        if not remediation_steps and final_disallowed > 0:
            remediation_steps = [
                f"Acknowledge the disallowed amount of ${final_disallowed:.2f} due to policy compliance limits."
            ]

        # Citations
        citations: list[PolicyCitation] = []
        cited_sections = set()
        for v in merged_violations:
            match = re.search(r"SEC-[\d\.]+", v.policy_section + " " + v.rule_id)
            if match:
                cited_sections.add(match.group(0))

        # If a transit exception was exercised in justification, cite SEC-2.2
        notes_lower = report.justification_notes.lower()
        if any(w in notes_lower for w in ["late night", "23:", "equipment", "lbs", "pounds", "booth"]):
            cited_sections.add("SEC-2.2")

        for s_id in sorted(cited_sections):
            citations.append(policy_retriever.create_citation(s_id))

        summary_text = qual_res_dict.get("audit_summary", "")
        if not summary_text or len(summary_text) < 10:
            if final_status == AuditStatus.APPROVED:
                summary_text = f"Report {report.report_id} complies with all enterprise T&E policies."
            else:
                summary_text = f"Report {report.report_id} audited: ${approved_amount:.2f} approved, ${final_disallowed:.2f} disallowed."

        final_audit = AuditResult(
            report_id=report.report_id,
            status=final_status,
            total_claimed=total_claimed,
            approved_amount=approved_amount,
            disallowed_amount=final_disallowed,
            violations=merged_violations,
            remediation_steps=remediation_steps,
            citations=citations,
            audit_summary=summary_text,
            confidence_score=0.98,
        )

        return {"final_result": final_audit}

    workflow = StateGraph(AuditorGraphState)
    workflow.add_node("retrieve", node_retrieve)
    workflow.add_node("deterministic_audit", node_deterministic_audit)
    workflow.add_node("qualitative_audit", node_qualitative_audit)
    workflow.add_node("synthesize", node_synthesize)

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "deterministic_audit")
    workflow.add_edge("deterministic_audit", "qualitative_audit")
    workflow.add_edge("qualitative_audit", "synthesize")
    workflow.add_edge("synthesize", END)

    return workflow.compile()


class AdvancedExpenseAuditor:
    """High-level interface to the compiled LangGraph compliance auditor."""

    def __init__(self, model_name: str | None = None):
        self.graph = create_expense_auditor_graph(model_name=model_name)

    def audit(self, report: ExpenseReport) -> AuditResult:
        state: AuditorGraphState = {
            "report": report,
            "policy_sections": [],
            "policy_context": "",
            "deterministic_violations": [],
            "deterministic_disallowed": 0.0,
            "qualitative_result": {},
            "final_result": None,
        }
        config = {
            "run_name": f"langgraph_audit_{report.report_id}",
            "tags": ["langgraph-auditor", report.department or "general"],
            "metadata": {"report_id": report.report_id, "employee_id": report.employee_id},
        }
        final_state = self.graph.invoke(state, config=config)
        return final_state["final_result"]
