from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .loan import RepaymentInstallmentResponse


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_email: str
    action: str
    entity_type: str
    entity_id: Optional[int]
    reason: Optional[str]
    is_platform_action: bool
    is_anomaly: bool
    created_at: datetime


class KYCOverrideRequest(BaseModel):
    # CLAUDE.md §8: override is exceptional and always reasoned — never optional.
    new_status: Literal["verified", "rejected"]
    reason: str = Field(min_length=1)


class ApplicationOverrideRequest(BaseModel):
    # MVP scope: only rejected -> approved ("reactivate a wrongly-rejected
    # application", the example CLAUDE.md §8 names). Reversing an approval
    # that already spawned a Loan would mean voiding that loan too — a much
    # bigger operation §8 doesn't ask for, so it's out of scope for now.
    reason: str = Field(min_length=1)


class AdminLoanResponse(BaseModel):
    id: int
    customer_full_name: str
    customer_email: str
    loan_product_name: str
    principal: Decimal
    total_repayable: Decimal
    # CLAUDE.md §23: 3-way breakdown — principal, base interest
    # (total_repayable - principal), and penalties, never one opaque number.
    penalties_accrued: Decimal
    outstanding_balance: Decimal
    status: str
    disbursed_at: Optional[datetime]
    created_at: datetime


class AdminLoanProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str]
    min_amount: Decimal
    max_amount: Decimal
    interest_rate: Decimal
    repayment_period_days: int
    is_active: bool
    # CLAUDE.md §23
    interest_model: str
    installment_count: int
    penalty_type: str
    penalty_rate: Decimal
    grace_period_days: int
    penalty_cap_ratio: Decimal
    # CLAUDE.md §26 (M13)
    branch_manager_delegated_limit: Decimal
    # CLAUDE.md §27 (M12)
    requires_guarantor: bool


class LoanProductCreateRequest(BaseModel):
    """CLAUDE.md §19: products are data rows a system_administrator edits,
    not values hard-coded in the app — every field a product needs is
    supplied at creation, not defaulted in silently."""

    name: str = Field(min_length=1)
    description: Optional[str] = None
    min_amount: Decimal = Field(gt=0)
    max_amount: Decimal = Field(gt=0)
    interest_rate: Decimal = Field(ge=0)
    repayment_period_days: int = Field(gt=0)
    interest_model: Literal["flat", "reducing_balance", "daily_accrual"] = "flat"
    installment_count: int = Field(default=1, gt=0)
    penalty_rate: Decimal = Field(default=Decimal("1.00"), ge=0)
    grace_period_days: int = Field(default=3, ge=0)
    penalty_cap_ratio: Decimal = Field(default=Decimal("1.00"), ge=0)
    branch_manager_delegated_limit: Decimal = Field(default=Decimal("100000.00"), ge=0)
    requires_guarantor: bool = False


class LoanProductUpdateRequest(BaseModel):
    # CLAUDE.md §19: products are data rows a system_administrator edits, not
    # values hard-coded in the app — every product-defining field is editable here.
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    interest_rate: Optional[Decimal] = None
    repayment_period_days: Optional[int] = Field(default=None, gt=0)
    is_active: Optional[bool] = None
    # CLAUDE.md §23 — Finance-revisable DEV placeholders live as config, so a
    # revised number is a config change here, never a code change.
    interest_model: Optional[Literal["flat", "reducing_balance", "daily_accrual"]] = None
    installment_count: Optional[int] = Field(default=None, gt=0)
    penalty_rate: Optional[Decimal] = Field(default=None, ge=0)
    grace_period_days: Optional[int] = Field(default=None, ge=0)
    penalty_cap_ratio: Optional[Decimal] = Field(default=None, ge=0)
    branch_manager_delegated_limit: Optional[Decimal] = Field(default=None, ge=0)
    requires_guarantor: Optional[bool] = None


class BranchCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    address: Optional[str] = None
    manager_id: Optional[int] = None
    # CLAUDE.md §26: optional override of the product default — a larger or
    # smaller/newer branch may be trusted with a different delegated limit.
    delegated_limit: Optional[Decimal] = Field(default=None, ge=0)


class BranchUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    address: Optional[str] = None
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None
    delegated_limit: Optional[Decimal] = Field(default=None, ge=0)


class BranchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    address: Optional[str]
    manager_id: Optional[int]
    is_active: bool
    delegated_limit: Optional[Decimal]
    created_at: datetime


class UserSummaryResponse(BaseModel):
    """system_administrator's own-company staff/customer breakdown — the
    same shape/computation as the platform-tier CompanyUserCounts
    (app/user_stats.py), just scoped by the automatic tenant filter here
    instead of an explicit company_id."""

    staff_total: int
    staff_active: int
    staff_inactive: int
    customer_total: int
    customer_active: int
    customer_inactive: int


class LoanCalculatorRequest(BaseModel):
    """CLAUDE.md §23: frontend never computes real money — this is a
    non-persisting preview that calls the exact same
    app/loan_calculation.py::generate_schedule dispatcher the real approval
    flow uses. No Loan/RepaymentSchedule rows are written."""

    principal: Decimal = Field(gt=0)
    interest_rate: Decimal = Field(ge=0)
    interest_model: Literal["flat", "reducing_balance", "daily_accrual"] = "flat"
    term_days: int = Field(gt=0)
    installment_count: int = Field(default=1, gt=0)
    start_date: Optional[date] = None


class LoanCalculatorResponse(BaseModel):
    principal: Decimal
    total_interest: Decimal
    total_repayable: Decimal
    schedule: list[RepaymentInstallmentResponse]


class AdminLoanDetailResponse(BaseModel):
    """Staff-facing loan detail — the same shape CustomerLoanResponse already
    gives the borrower on /loans/me, just for staff (system_administrator,
    this round). No CRUD on the live loan record itself — see the schedule's
    own amount_paid/is_paid fields, which come from the real repayment
    ledger, never hand-edited."""

    id: int
    customer_full_name: str
    customer_email: str
    loan_product_name: str
    principal: Decimal
    interest_rate: Decimal
    total_repayable: Decimal
    penalties_accrued: Decimal
    outstanding_balance: Decimal
    status: str
    disbursed_at: Optional[datetime]
    created_at: datetime
    schedule: list[RepaymentInstallmentResponse]
