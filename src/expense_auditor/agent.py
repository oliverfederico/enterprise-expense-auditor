"""Initial compliance auditor agent for reviewing corporate expense reports."""

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from expense_auditor.config import settings
from expense_auditor.models.expense import ExpenseReport
from expense_auditor.models.audit import AuditResult, AuditStatus
from expense_auditor.rag.retriever import PolicyRetriever


SYSTEM_AUDIT_PROMPT = """You are an Enterprise Expense Policy Compliance Auditor.
Your job is to review submitted corporate expense reports, itemized receipts, and employee justification notes against the company's official Travel & Expense (T&E) Policy clauses provided below.

### COMPANY POLICY CLAUSES:
{policy_context}

### AUDIT INSTRUCTIONS:
1. Examine each receipt in the report (amounts, line items, dates, times, categories, vendor, itemization).
2. Check compliance against all applicable policy clauses:
   - Daily per diem cap ($75/day for individual meals).
   - Alcohol cap (maximum 20% of meal subtotal; forbidden at solo breakfast/lunch).
   - Ground transportation (rideshares disallowed if public transit is under 15 minutes, unless valid exceptions apply: 10 PM - 6 AM, bulky equipment >30 lbs, or verified safety hazards).
   - Client entertainment ($150 per person limit, mandatory full attendee names/titles/affiliations, detailed business justification).
   - Documentation (itemized receipts required for meal expenses > $25).
3. If an expense violates a policy clause, create a Violation with the specific rule ID, section name, severity, factual evidence, and calculate the disallowed amount.
4. Calculate:
   - `total_claimed`: Total amount of all receipts submitted.
   - `disallowed_amount`: Total sum of all disallowed non-compliant expenditures.
   - `approved_amount`: `total_claimed - disallowed_amount`.
5. Determine `status`:
   - `APPROVED`: Fully compliant with all policies.
   - `FLAGGED_FOR_REVIEW`: Missing information (e.g., missing attendee list, non-itemized receipt > $25) or borderline justification requiring manager clarification.
   - `REJECTED`: Clear policy violations present or intentional evasion.
6. Provide clear, polite, and actionable `remediation_steps` if the employee needs to supply documentation or rectify a claim.
7. Provide a concise `audit_summary` explaining the decision.
"""


USER_AUDIT_PROMPT = """Please audit the following employee expense report:

REPORT METADATA:
- Report ID: {report_id}
- Employee: {employee_name} ({employee_id})
- Department: {department}
- Submission Date: {submission_date}
- Trip Purpose: {trip_purpose}
- Route: {origin} -> {destination}
- Justification Notes: {justification_notes}
- Documented Attendees: {attendees}

SUBMITTED RECEIPTS:
{receipts_detail}
"""


class ExpenseAuditorAgent:
    """Compliance auditor agent combining RAG policy retrieval and LLM reasoning."""

    def __init__(
        self,
        retriever: PolicyRetriever | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
    ):
        self.retriever = retriever or PolicyRetriever()
        model = model_name or settings.gemini_model
        temp = settings.gemini_temperature if temperature is None else temperature

        self.llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.google_api_key,
            temperature=temp,
        )
        self.structured_llm = self.llm.with_structured_output(AuditResult)

    def _format_receipts(self, report: ExpenseReport) -> str:
        lines = []
        for idx, r in enumerate(report.receipts, 1):
            time_str = f" at {r.time}" if r.time else ""
            lines.append(
                f"Receipt #{idx} [{r.receipt_id}]: {r.vendor} on {r.date}{time_str} | Category: {r.category.value}"
            )
            lines.append(
                f"  Subtotal: ${r.subtotal:.2f}, Tax: ${r.tax:.2f}, Tip: ${r.tip:.2f}, Total: ${r.total_amount:.2f} {r.currency}"
            )
            lines.append(f"  Itemized: {'Yes' if r.is_itemized else 'No (Summary slip only)'}")
            if r.line_items:
                lines.append("  Line Items:")
                for item in r.line_items:
                    alcohol_tag = " [ALCOHOL]" if item.is_alcohol else ""
                    lines.append(f"    - {item.description}: ${item.amount:.2f}{alcohol_tag}")
            elif r.raw_text:
                lines.append(f"  Raw Text: {r.raw_text}")
            lines.append("")
        return "\n".join(lines)

    def audit(self, report: ExpenseReport) -> AuditResult:
        """Audits an expense report against retrieved company policies."""
        # Step 1: Policy Retrieval (RAG)
        policy_sections = self.retriever.retrieve_for_report(report)
        policy_context = self.retriever.format_policies_for_prompt(policy_sections)

        # Step 2: Format prompt
        receipts_detail = self._format_receipts(report)
        attendees_str = ", ".join(report.attendees) if report.attendees else "None listed"

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_AUDIT_PROMPT),
                ("user", USER_AUDIT_PROMPT),
            ]
        )

        formatted_messages = prompt.format_messages(
            policy_context=policy_context,
            report_id=report.report_id,
            employee_name=report.employee_name,
            employee_id=report.employee_id,
            department=report.department or "N/A",
            submission_date=report.submission_date,
            trip_purpose=report.trip_purpose,
            origin=report.origin or "N/A",
            destination=report.destination or "N/A",
            justification_notes=report.justification_notes or "None provided",
            attendees=attendees_str,
            receipts_detail=receipts_detail,
        )

        # Step 3: LLM Structured Audit Decision
        config = {
            "run_name": f"audit_report_{report.report_id}",
            "tags": ["baseline-auditor", report.department or "general"],
            "metadata": {"report_id": report.report_id, "employee_id": report.employee_id},
        }
        result = self.structured_llm.invoke(formatted_messages, config=config)

        # Ensure report_id matches
        if not result.report_id:
            result.report_id = report.report_id

        return result
