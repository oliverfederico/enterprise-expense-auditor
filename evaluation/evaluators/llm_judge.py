"""LLM Judge for qualitative evaluation of expense compliance decisions."""

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from expense_auditor.config import settings
from expense_auditor.models.audit import AuditResult


class JudgeEvaluation(BaseModel):
    policy_groundedness_score: int = Field(
        ge=1, le=5, description="1-5 rating: Are all citations and reasoning strictly grounded in policy?"
    )
    remediation_actionability_score: int = Field(
        ge=1, le=5, description="1-5 rating: Are remediation instructions clear, respectful, and actionable?"
    )
    judgment_agreement: bool = Field(
        description="True if the judge agrees with the auditor's qualitative interpretation of notes and exceptions"
    )
    judge_critique: str = Field(description="Detailed rationale from the LLM judge")


JUDGE_SYSTEM_PROMPT = """You are a Senior Internal Audit Director acting as an LLM Judge.
Your responsibility is to critically evaluate automated compliance audit decisions produced by an AI Expense Auditor.

Assess the decision across three dimensions:
1. Policy Groundedness (1-5):
   - 5: Flawlessly grounded in company T&E policy; no hallucinated rules or fake limits.
   - 3: Mostly grounded, but mentions uncodified assumptions or minor inaccuracies.
   - 1: Severe hallucinations or cited policies that do not exist.
2. Remediation Actionability (1-5):
   - 5: Courteous, constructive, and specifies exactly what documentation (e.g. itemized receipt, attendee names) is required.
   - 3: Vague instructions (e.g. 'follow policy') without concrete next steps.
   - 1: Unhelpful, rude, or misleading feedback.
3. Judgment Agreement (Boolean):
   - True if the auditor correctly interpreted qualitative nuances (such as whether a late-night timestamp justifies a rideshare, or whether attendee notes are adequate).
"""

JUDGE_USER_PROMPT = """Please evaluate this audit decision:

TEST SCENARIO:
- Case ID: {case_id}
- Description: {description}
- Ground Truth Expected Outcome: {expected_notes}

AUDITOR DECISION:
- Status: {status}
- Claimed: ${total_claimed:.2f} | Approved: ${approved:.2f} | Disallowed: ${disallowed:.2f}
- Summary: {summary}
- Violations: {violations}
- Remediation Steps: {remediation}
"""


class ComplianceLLMJudge:
    """Evaluates qualitative performance of expense audit decisions."""

    def __init__(self, model_name: str | None = None):
        model = model_name or settings.gemini_model
        self.llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.google_api_key,
            temperature=0.0,
        )
        self.structured_judge = self.llm.with_structured_output(JudgeEvaluation)

    def evaluate(self, result: AuditResult, test_case: dict) -> JudgeEvaluation:
        violations_str = "\n".join(
            f"- {v.rule_id} ({v.policy_section}): {v.description} [Disallowed: ${v.disallowed_amount:.2f}]"
            for v in result.violations
        ) or "None"

        remediation_str = "\n".join(f"- {s}" for s in result.remediation_steps) or "None"

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", JUDGE_SYSTEM_PROMPT),
                ("user", JUDGE_USER_PROMPT),
            ]
        )

        messages = prompt.format_messages(
            case_id=test_case["case_id"],
            description=test_case["description"],
            expected_notes=test_case["expected"]["notes"],
            status=result.status.value,
            total_claimed=result.total_claimed,
            approved=result.approved_amount,
            disallowed=result.disallowed_amount,
            summary=result.audit_summary,
            violations=violations_str,
            remediation=remediation_str,
        )

        config = {
            "run_name": f"llm_judge_{test_case.get('case_id', 'TC')}",
            "tags": ["llm-judge", test_case.get("slice", "general")],
            "metadata": {"case_id": test_case.get("case_id", "TC")},
        }
        return self.structured_judge.invoke(messages, config=config)
