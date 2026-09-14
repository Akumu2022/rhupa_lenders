import enum
from typing import Optional

from sqlmodel import Field, SQLModel


class CompanyStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"


class Company(SQLModel, table=True):
    """The tenant root (CLAUDE.md §5). Does NOT inherit TenantMixin — it IS the
    thing every other tenant-owned row is scoped by."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    status: CompanyStatus = Field(default=CompanyStatus.active, index=True)

    # CLAUDE.md §7: >=10 chars of real entropy (secrets.token_urlsafe / Crockford
    # base32), never sequential — it's the sole gate that assigns company_id at signup.
    signup_code: str = Field(index=True, unique=True)

    # CLAUDE.md §21: tenant profile + branding. super_admin sets all of this at
    # creation; system_administrator may later edit the client-facing subset (contacts,
    # address, logo, brand colors) via PATCH /companies/me — never name,
    # legal_name, registration_number, or signup_code. A handful of DATA values
    # only — the platform's fixed design-token system is what actually renders
    # them (never per-tenant CSS/layout).
    legal_name: Optional[str] = None
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None  # "#RRGGBB", validated in the request schemas
    brand_accent_color: Optional[str] = None
    support_email: Optional[str] = None
    support_phone: Optional[str] = None
    address: Optional[str] = None
    registration_number: Optional[str] = None

    # CLAUDE.md §27 (M11): the counter behind app/customer_registration.py's
    # next_customer_number() — incremented via compare-and-set (rule #14),
    # never read-then-blindly-written. Starts at 1, not 0, so the first
    # generated number is CUST-{company_id:04d}-000001.
    next_customer_sequence: int = Field(default=1)
