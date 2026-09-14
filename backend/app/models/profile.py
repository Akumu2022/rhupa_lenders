import enum
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class KYCStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class Profile(TenantMixin, table=True):
    """CLAUDE.md M2: customer profile intake (personal/contact/economic) plus
    KYC review state. One profile per customer (`user_id` is unique).

    CLAUDE.md §27 (M11): extended with the client PRD's full registration
    field set. Every M11 field below is nullable at the DB layer — the
    original self-signup `/profile` submission (M2) still only requires the
    first seven fields above; the new credit-officer registration endpoint
    (app/routers/customers.py) is what actually requires the fuller set, at
    its own Pydantic validation layer, not here.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, unique=True)

    date_of_birth: date
    national_id_number: str = Field(index=True)
    phone_number: str
    residential_address: str

    employment_status: str
    monthly_income: Decimal = Field(max_digits=12, decimal_places=2)
    occupation: str

    # Paths on disk under settings.kyc_storage_root — never a served URL
    # (CLAUDE.md §9, §16). Served later only via an authenticated,
    # tenant-scoped, role-gated endpoint (M3). `selfie_path` doubles as the
    # client PRD's "customer photograph where legally appropriate" (§27) —
    # no separate photo field.
    id_document_path: str  # ID front
    # Nullable at the DB layer only for profiles submitted before this field
    # existed — the submission form requires it for every new profile.
    id_document_back_path: Optional[str] = None
    selfie_path: Optional[str] = None

    # CLAUDE.md §11: every reviewable entity carries status + reviewer fields.
    kyc_status: KYCStatus = Field(default=KYCStatus.pending, index=True)
    reviewed_by: Optional[int] = Field(default=None, foreign_key="user.id")
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

    # --- CLAUDE.md §27 (M11): client PRD §2A extended registration fields ---
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    id_type: Optional[str] = None  # "national_id" | "passport" — free string like employment_status
    gender: Optional[str] = None
    nationality: Optional[str] = None
    marital_status: Optional[str] = None
    dependants_count: Optional[int] = None
    phone_number_alt: Optional[str] = None
    next_of_kin_name: Optional[str] = None
    next_of_kin_relationship: Optional[str] = None
    next_of_kin_phone: Optional[str] = None
    # Generated once, at first creation (either registration path), via
    # app/customer_registration.py::next_customer_number — never regenerated
    # on a post-rejection resubmission (identifies the person, not the KYC
    # attempt). Unique per company, enforced at the migration layer.
    customer_number: Optional[str] = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
