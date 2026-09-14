from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class Referee(TenantMixin, table=True):
    """CLAUDE.md §27 (M11): client PRD §2A "Referees" — an open-ended list per
    profile, unlike "next of kin" (one primary contact, kept inline on
    Profile). Captured by whichever flow registers the customer
    (self-signup or credit-officer registration); no review/verification
    status of its own in the MVP.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    full_name: str
    phone_number: str
    relationship: Optional[str] = None
    address: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
