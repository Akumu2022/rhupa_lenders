from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class Branch(TenantMixin, table=True):
    """CLAUDE.md §25: a company-scoped organizational unit, NOT a tenant
    isolation boundary — company_id (via TenantMixin) is the only hard wall
    (§5). Staff (credit_officer, branch_manager) are assigned to a Branch;
    company-wide roles leave User.branch_id null.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    code: str = Field(index=True)  # unique per company, enforced at the DB layer via migration
    address: Optional[str] = None
    manager_id: Optional[int] = Field(default=None, foreign_key="user.id")
    is_active: bool = Field(default=True)

    # CLAUDE.md §26: an optional per-branch override of the product's own
    # branch_manager_delegated_limit — a larger or smaller/newer branch may
    # be trusted with a different limit. The effective limit for a given
    # application is min(this, product's default) when both are set, never
    # silently the larger/looser figure.
    delegated_limit: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
