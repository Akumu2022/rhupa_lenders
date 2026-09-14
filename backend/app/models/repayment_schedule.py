from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field

from ..tenancy import TenantMixin


class RepaymentSchedule(TenantMixin, table=True):
    """CLAUDE.md M5: generated at approval time. One installment per loan for
    the MVP's simple short-term products (a single bullet repayment) — the
    schema already supports multiple installments without changes if products
    grow more complex later.

    The (is_paid, due_date) index backs app/loan_delinquency.py's
    `WHERE is_paid = false AND due_date < :today` query — the single most
    frequently executed query in the app, run from nearly every read path
    that touches loans.
    """

    __table_args__ = (Index("ix_repaymentschedule_is_paid_due_date", "is_paid", "due_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    loan_id: int = Field(foreign_key="loan.id", index=True)
    installment_number: int = Field(default=1)
    due_date: date
    amount_due: Decimal = Field(max_digits=12, decimal_places=2)
    amount_paid: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)
    # CLAUDE.md §19 borrower transparency: the principal/interest split of
    # amount_due for this installment, so customers see a real amortization
    # breakdown rather than just "amount due". Set once at creation time
    # (create_loan_for_application); the two always sum to amount_due.
    principal_component: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)
    interest_component: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)
    is_paid: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
