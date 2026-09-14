import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class TransactionType(str, enum.Enum):
    disbursement = "disbursement"
    repayment = "repayment"
    # CLAUDE.md §23: each daily penalty application is its own ledger row —
    # the owed amount never grows silently. Written only by
    # app/loan_calculation.py::apply_daily_penalties.
    penalty = "penalty"


class Transaction(TenantMixin, table=True):
    """CLAUDE.md §15 core entity, ledger for the simulated money movements.

    M7 (disbursement & repayment) is what writes rows here — "everything
    external is simulated... but simulated actions still write ledger + audit
    rows" (rule #9). M6's customer dashboard only reads this table, so it is
    legitimately empty until M7 ships.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    loan_id: int = Field(foreign_key="loan.id", index=True)
    customer_id: int = Field(foreign_key="user.id", index=True)
    type: TransactionType
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
