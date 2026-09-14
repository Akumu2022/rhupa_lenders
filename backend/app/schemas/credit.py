from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from ..models import ApplicationStatus


class CreditDecisionRequest(BaseModel):
    # CLAUDE.md §9: credit officer approve/reject both require notes — unlike
    # KYC verify, there is no "no comment" path here.
    notes: str = Field(min_length=1)


class CreditApplicationResponse(BaseModel):
    id: int
    customer_full_name: str
    customer_email: str
    loan_product_name: str
    amount_requested: Decimal
    status: ApplicationStatus
    review_notes: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime
    # None until the application is approved and a Loan exists for it — lets
    # the frontend distinguish "approved, awaiting disbursement" from
    # "disbursed" (and later overdue/defaulted/repaid) instead of collapsing
    # every approved application into one ambiguous "approved" badge.
    loan_status: Optional[str] = None


class LoanResponse(BaseModel):
    id: int
    application_id: int
    principal: Decimal
    interest_rate: Decimal
    total_repayable: Decimal
    # CLAUDE.md §23: 3-way breakdown — principal, base interest
    # (total_repayable - principal), and penalties, never one opaque number.
    penalties_accrued: Decimal
    outstanding_balance: Decimal
    status: str
    disbursed_at: Optional[datetime] = None


class LoanApprovalResponse(BaseModel):
    application: CreditApplicationResponse
    loan: LoanResponse
    repayment_due_date: date
    repayment_amount_due: Decimal


class DisbursementResponse(BaseModel):
    loan: LoanResponse


class PendingDisbursementResponse(BaseModel):
    id: int
    customer_full_name: str
    customer_email: str
    loan_product_name: str
    principal: Decimal
    total_repayable: Decimal
    created_at: datetime


class LoanDefaultRequest(BaseModel):
    # CLAUDE.md §19/§1: marking a loan defaulted is a human decision, always
    # reasoned and audited — never automatic.
    reason: str = Field(min_length=1)


class CollectionsQueueItemResponse(BaseModel):
    id: int
    customer_full_name: str
    customer_email: str
    loan_product_name: str
    outstanding_balance: Decimal
    status: str
    earliest_overdue_due_date: date
    days_overdue: int
