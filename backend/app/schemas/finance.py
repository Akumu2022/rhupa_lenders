from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from ..models import ExpenseCategory


class ExpenseCreateRequest(BaseModel):
    category: ExpenseCategory
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    description: Optional[str] = None
    branch_id: Optional[int] = None


class ExpenseResponse(BaseModel):
    id: int
    category: ExpenseCategory
    amount: Decimal
    description: Optional[str]
    branch_id: Optional[int]
    created_by_name: str
    created_at: datetime


class FinancialsResponse(BaseModel):
    # CLAUDE.md §30: derived read-only from Transaction (income) +
    # ExpenseEntry (expenses) — never a second ledger. Transaction doesn't
    # split a repayment into its principal/interest components (that split
    # only exists per-installment on RepaymentSchedule), so income here is
    # reported the two ways Transaction actually itemizes it: repayments
    # collected and penalties collected.
    period_start: str
    total_repayment_income: Decimal
    total_penalty_income: Decimal
    total_disbursed: Decimal
    total_expenses: Decimal
    net: Decimal
    recent_expenses: list[ExpenseResponse]
