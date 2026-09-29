from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class MfaRecoveryCode(TenantMixin, table=True):
    """One-time-use MFA recovery codes, issued 10-at-a-time on
    /auth/mfa/confirm. Stored hashed (via app/security.py::hash_password,
    same as the user's own password) — the plain codes are shown to the
    user exactly once, at issuance, and never again. `used_at` makes a code
    single-use: checked and stamped atomically at verification time.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    code_hash: str
    used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
