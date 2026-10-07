"""Domain models for audit outcomes, violations, and remediation."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from expense_auditor.models.policy import PolicyCitation


class AuditStatus(str, Enum):
    APPROVED = "APPROVED"
    FLAGGED_FOR_REVIEW = "FLAGGED_FOR_REVIEW"
    REJECTED = "REJECTED"


class ViolationSeverity(str, Enum):
    HARD_VIOLATION = "HARD_VIOLATION"      # Outright non-compliant or disallowable
    SOFT_WARNING = "SOFT_WARNING"          # Warning / advisory note
    MISSING_INFO = "MISSING_INFO"          # Missing receipts, attendee names, etc.


class Violation(BaseModel):
    rule_id: str = Field(description="Code for the rule violated, e.g., 'VIO-ALCOHOL-CAP'")
    policy_section: str = Field(description="Policy section cited, e.g., 'SEC-1.2: Alcohol Policy'")
    severity: ViolationSeverity
    description: str
    evidence: str = Field(description="Factual evidence extracted from the receipt or notes")
    disallowed_amount: float = Field(default=0.0, ge=0.0)


class AuditResult(BaseModel):
    report_id: str
    status: AuditStatus
    total_claimed: float = Field(ge=0.0)
    approved_amount: float = Field(ge=0.0)
    disallowed_amount: float = Field(default=0.0, ge=0.0)
    violations: list[Violation] = Field(default_factory=list)
    remediation_steps: list[str] = Field(
        default_factory=list,
        description="Actionable steps for employee to resolve issues or submit missing documentation",
    )
    citations: list[PolicyCitation] = Field(default_factory=list)
    audit_summary: str
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
