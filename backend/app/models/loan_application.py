import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class ApplicationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class LoanApplication(TenantMixin, table=True):
    """CLAUDE.md M4/§10: Handoff 2 — submission writes status=pending; the
    credit officer queue (M5) is just a filtered query over this field.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="user.id", index=True)
    loan_product_id: int = Field(foreign_key="loanproduct.id", index=True)
    amount_requested: Decimal = Field(max_digits=12, decimal_places=2)

    # CLAUDE.md §11: every reviewable entity carries status + reviewer fields.
    status: ApplicationStatus = Field(default=ApplicationStatus.pending, index=True)
    reviewed_by: Optional[int] = Field(default=None, foreign_key="user.id")
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

    # Indexed — every oversight/queue endpoint sorts on this (ORDER BY
    # created_at [DESC]); senior-review finding, previously unindexed.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
