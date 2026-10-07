"""Domain models for corporate policy rules and citations."""

from typing import Optional
from pydantic import BaseModel, Field
from expense_auditor.models.expense import ExpenseCategory


class PolicySection(BaseModel):
    section_id: str = Field(description="Unique policy identifier, e.g., 'SEC-1.1'")
    title: str = Field(description="Title of the policy section")
    content: str = Field(description="Full text of the policy clause")
    category: ExpenseCategory = ExpenseCategory.OTHER
    keywords: list[str] = Field(default_factory=list)


class PolicyCitation(BaseModel):
    section_id: str
    title: str
    relevant_clause: str
    explanation: Optional[str] = None
