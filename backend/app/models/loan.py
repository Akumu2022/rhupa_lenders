import enum
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class LoanStatus(str, enum.Enum):
    approved = "approved"
    active = "active"
    overdue = "overdue"
    defaulted = "defaulted"
    repaid = "repaid"


class Loan(TenantMixin, table=True):
    """CLAUDE.md §11/§19 status ladder: approved -> active -> overdue ->
    defaulted, with repaid reachable from active/overdue/defaulted at any
    point. Created on credit-officer approval (M5) with status=approved;
    disbursement (M7) moves it to active — approval itself never fakes a
    disbursement. active -> overdue is a system-computed transition (see
    app/loan_delinquency.py); overdue -> defaulted is always an explicit,
    reasoned staff action (§1: automation is advisory, humans decide).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="loanapplication.id", index=True, unique=True)
    customer_id: int = Field(foreign_key="user.id", index=True)
    loan_product_id: int = Field(foreign_key="loanproduct.id", index=True)

    principal: Decimal = Field(max_digits=12, decimal_places=2)
    interest_rate: Decimal = Field(max_digits=5, decimal_places=2)  # snapshot at approval time
    total_repayable: Decimal = Field(max_digits=12, decimal_places=2)  # principal + base interest, NEVER includes penalties
    outstanding_balance: Decimal = Field(max_digits=12, decimal_places=2)  # total currently owed: total_repayable + penalties_accrued - payments

    # CLAUDE.md §23: penalties are tracked separately from base interest so
    # the owed amount is always shown as a 3-way breakdown (principal / base
    # interest / penalties), never one opaque number. app/loan_calculation.py
    # is the only writer of these two fields.
    penalties_accrued: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)
    last_penalty_check_date: Optional[date] = None

    # Column width auto-sizes to the longest member ("defaulted" = 9 chars)
    # on a fresh install; an existing Postgres column from before this change
    # was VARCHAR(8) and needs its migration to widen it explicitly — unlike
    # SQLite, Postgres actually enforces VARCHAR(n).
    status: LoanStatus = Field(default=LoanStatus.approved, index=True)
    disbursed_at: Optional[datetime] = None
    # Indexed — every oversight/queue endpoint sorts on this (ORDER BY
    # created_at [DESC]); senior-review finding, previously unindexed.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
