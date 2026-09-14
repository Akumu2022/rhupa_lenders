import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class ExpenseCategory(str, enum.Enum):
    salaries = "salaries"
    rent = "rent"
    transport = "transport"
    communications = "communications"
    administration = "administration"
    other = "other"


class ExpenseEntry(TenantMixin, table=True):
    """CLAUDE.md §30: cashier/finance officer's expense ledger — cashbook and
    income-statement views are derived read-only from Transaction (income)
    + this table (expenses), never a second source of truth for money
    already tracked elsewhere.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    branch_id: Optional[int] = Field(default=None, foreign_key="branch.id", index=True)
    category: ExpenseCategory
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    description: Optional[str] = None
    created_by: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
