from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class BranchCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    address: Optional[str] = None
    manager_id: Optional[int] = None


class BranchUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    address: Optional[str] = None
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None


class BranchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    address: Optional[str]
    manager_id: Optional[int]
    is_active: bool
    created_at: datetime


class PortfolioTrendPoint(BaseModel):
    date: date
    disbursed_count: int
    disbursed_amount: Decimal


class PortfolioTrendResponse(BaseModel):
    # CLAUDE.md §20: the sparkline behind the portfolio hero stat — daily
    # disbursement activity over the trailing window.
    points: list[PortfolioTrendPoint]


class PortfolioSummaryResponse(BaseModel):
    # CLAUDE.md §9: aggregates only, no individual PII on this screen.
    total_disbursed: Decimal
    total_collected: Decimal
    active_borrowers: int
    active_loans: int
    outstanding_principal: Decimal
    par_percentage: Decimal  # portfolio-at-risk: overdue outstanding / total outstanding
    overdue_loans: int
    defaulted_loans: int
    loans_disbursed_this_month: int
    as_of: date
