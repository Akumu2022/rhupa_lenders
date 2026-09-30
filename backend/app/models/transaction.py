import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from ..tenancy import TenantMixin


class TransactionType(str, enum.Enum):
    disbursement = "disbursement"
    repayment = "repayment"
    # CLAUDE.md §23: each daily penalty application is its own ledger row —
    # the owed amount never grows silently. Written only by
    # app/loan_calculation.py::apply_daily_penalties.
    penalty = "penalty"


class PaymentMethod(str, enum.Enum):
    """How a repayment reached the lender. `customer_portal` is the
    customer's own self-service "repay now" (still simulated, CLAUDE.md §1);
    the rest are recorded by staff who received the money."""

    customer_portal = "customer_portal"
    cash = "cash"
    mpesa = "mpesa"
    bank = "bank"


class Transaction(TenantMixin, table=True):
    """CLAUDE.md §15 core entity, ledger for the simulated money movements.

    M7 (disbursement & repayment) is what writes rows here — "everything
    external is simulated... but simulated actions still write ledger + audit
    rows" (rule #9). M6's customer dashboard only reads this table, so it is
    legitimately empty until M7 ships.
    """

    # One external payment reference (e.g. an M-Pesa code) can be recorded
    # once per company — the guard against the same payment being keyed in
    # twice. NULL references (disbursements, penalties, cash without a slip)
    # never collide: NULLs are distinct in a unique constraint on both
    # SQLite and Postgres.
    __table_args__ = (
        UniqueConstraint("company_id", "reference", name="uq_transaction_company_reference"),
        UniqueConstraint("company_id", "receipt_number", name="uq_transaction_company_receipt"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    loan_id: int = Field(foreign_key="loan.id", index=True)
    customer_id: int = Field(foreign_key="user.id", index=True)
    type: TransactionType
    amount: Decimal = Field(max_digits=12, decimal_places=2)

    # Repayment-only fields (null on disbursement/penalty rows).
    method: Optional[PaymentMethod] = None
    reference: Optional[str] = Field(default=None, max_length=64)
    receipt_number: Optional[str] = Field(default=None, max_length=32)
    # The staff member who received and recorded the payment; null when the
    # customer paid through their own portal.
    recorded_by: Optional[int] = Field(default=None, foreign_key="user.id")
    notes: Optional[str] = Field(default=None, max_length=500)
    # How a repayment was split (penalties -> interest -> principal). Null on
    # non-repayment rows and on repayments recorded before the split existed.
    penalty_portion: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    interest_portion: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    principal_portion: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
