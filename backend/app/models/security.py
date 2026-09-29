from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class Security(TenantMixin, table=True):
    """CLAUDE.md §27 (M12): a pledged collateral asset tied to one specific
    loan application. `document_path` follows the same authenticated-file
    pattern as KYC documents (app/kyc_storage.py) — never a static/guessable
    path, per rule #16.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="loanapplication.id", index=True)

    description: str
    estimated_value: Decimal = Field(max_digits=12, decimal_places=2)
    document_path: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
