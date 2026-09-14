from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ..models import ApplicationStatus


class LoanProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str]
    min_amount: Decimal
    max_amount: Decimal
    interest_rate: Decimal
    repayment_period_days: int
    # CLAUDE.md §19 upfront term transparency: shown to the customer before
    # they apply, not just derived after approval.
    interest_model: str
    installment_count: int


class LoanApplicationCreateRequest(BaseModel):
    loan_product_id: int
    amount_requested: Decimal = Field(gt=0)


class LoanApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    loan_product_id: int
    amount_requested: Decimal
    status: ApplicationStatus
    review_notes: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime


class RepaymentInstallmentResponse(BaseModel):
    id: int
    installment_number: int
    due_date: date
    amount_due: Decimal
    amount_paid: Decimal
    # CLAUDE.md §19 borrower transparency: principal vs interest, not just a
    # lump "amount due". principal_component + interest_component == amount_due.
    principal_component: Decimal
    interest_component: Decimal
    is_paid: bool


class CustomerLoanResponse(BaseModel):
    id: int
    loan_product_name: str
    principal: Decimal
    interest_rate: Decimal
    total_repayable: Decimal
    # CLAUDE.md §23: 3-way breakdown — principal, base interest
    # (total_repayable - principal), and penalties, never one opaque number.
    penalties_accrued: Decimal
    outstanding_balance: Decimal
    status: str
    disbursed_at: Optional[datetime]
    created_at: datetime
    schedule: list[RepaymentInstallmentResponse]


class RepaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)


class RepaymentResponse(BaseModel):
    loan_id: int
    amount_paid_now: Decimal
    outstanding_balance: Decimal
    status: str


class CustomerCreditSummaryResponse(BaseModel):
    # CLAUDE.md §9/§1: no credit scoring exists yet — `loan_limit` is not a
    # score, just the largest amount any active product in this company
    # offers. `available_credit` nets out what the customer currently owes
    # on active loans. A real scoring model (advisory only, per rule #8) can
    # replace this heuristic later without changing the response shape.
    loan_limit: Decimal
    available_credit: Decimal
    standing: str
    loans: list[CustomerLoanResponse]
