"""Domain models for expense claims, receipts, and line items."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class ExpenseCategory(str, Enum):
    MEALS = "MEALS"
    ALCOHOL = "ALCOHOL"
    GROUND_TRANSIT = "GROUND_TRANSIT"
    LODGING = "LODGING"
    FLIGHT = "FLIGHT"
    CLIENT_ENTERTAINMENT = "CLIENT_ENTERTAINMENT"
    INCIDENTAL = "INCIDENTAL"
    OTHER = "OTHER"


class ReceiptLineItem(BaseModel):
    description: str
    amount: float = Field(ge=0.0)
    category: ExpenseCategory = ExpenseCategory.OTHER
    is_alcohol: bool = False
    quantity: int = Field(default=1, ge=1)


class Receipt(BaseModel):
    receipt_id: str
    vendor: str
    date: str = Field(description="Transaction date in YYYY-MM-DD format")
    time: Optional[str] = Field(default=None, description="Transaction time in HH:MM format (24-hr)")
    category: ExpenseCategory
    subtotal: float = Field(ge=0.0)
    tax: float = Field(default=0.0, ge=0.0)
    tip: float = Field(default=0.0, ge=0.0)
    total_amount: float = Field(ge=0.0)
    currency: str = Field(default="USD")
    is_itemized: bool = True
    line_items: list[ReceiptLineItem] = Field(default_factory=list)
    raw_text: Optional[str] = None

    @model_validator(mode="after")
    def validate_totals(self) -> "Receipt":
        # Ensure subtotal is consistent if total was provided without subtotal
        if self.subtotal == 0.0 and self.total_amount > 0.0:
            self.subtotal = max(0.0, self.total_amount - self.tax - self.tip)
        return self


class ExpenseReport(BaseModel):
    report_id: str
    employee_id: str
    employee_name: str
    department: Optional[str] = None
    submission_date: str = Field(description="Submission date in YYYY-MM-DD format")
    trip_purpose: str
    origin: Optional[str] = None
    destination: Optional[str] = None
    receipts: list[Receipt] = Field(default_factory=list)
    justification_notes: str = ""
    attendees: list[str] = Field(
        default_factory=list,
        description="Attendee names and affiliations, required for client entertainment",
    )

    @property
    def total_claimed(self) -> float:
        return round(sum(r.total_amount for r in self.receipts), 2)
