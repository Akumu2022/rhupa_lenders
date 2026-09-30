import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from ..models import CompanyStatus, UserRole

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validate_hex_color(value: Optional[str]) -> Optional[str]:
    # CLAUDE.md §21: tenant supplies DATA (a color), the platform controls the
    # MECHANISM — a bad value can't turn into broken CSS or unreadable text,
    # it's just rejected at the door.
    if value is not None and not _HEX_COLOR_RE.match(value):
        raise ValueError("Color must be a hex value like #4F46E5")
    return value


class CompanyBrandingFields(BaseModel):
    """CLAUDE.md §21: the client-facing subset a system_administrator may edit later
    — never name, legal_name, registration_number, or signup_code."""

    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None
    brand_accent_color: Optional[str] = None
    support_email: Optional[EmailStr] = None
    support_phone: Optional[str] = None
    address: Optional[str] = None

    _validate_primary = field_validator("brand_primary_color")(_validate_hex_color)
    _validate_accent = field_validator("brand_accent_color")(_validate_hex_color)


class CompanyCreateRequest(CompanyBrandingFields):
    name: str = Field(min_length=1)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)
    admin_full_name: str = Field(min_length=1)
    # Identity fields only super_admin sets, at creation — system_administrator
    # cannot change these later via the branding-edit endpoint.
    legal_name: Optional[str] = None
    registration_number: Optional[str] = None


class CompanyProfileUpdateRequest(CompanyBrandingFields):
    """PATCH /companies/me — system_administrator only, client-facing subset only."""


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: CompanyStatus
    signup_code: str
    legal_name: Optional[str] = None
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None
    brand_accent_color: Optional[str] = None
    support_email: Optional[str] = None
    support_phone: Optional[str] = None
    address: Optional[str] = None
    registration_number: Optional[str] = None
    created_at: datetime


class CompanyUserCounts(BaseModel):
    """Staff vs. customer breakdown, further split by active/inactive — the
    platform company-detail screen's headline stat cards."""

    staff_total: int
    staff_active: int
    staff_inactive: int
    customer_total: int
    customer_active: int
    customer_inactive: int


class CompanyDetailResponse(CompanyResponse):
    users: CompanyUserCounts


class CompanyUserRow(BaseModel):
    """One row of the company-detail user table — deliberately not the full
    UserResponse shape (no branch_id noise on a cross-company screen)."""

    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool


class CompanyActivityPoint(BaseModel):
    date: date
    audit_log_count: int


class CompanyActivityResponse(BaseModel):
    """CLAUDE.md §12: every privileged action already writes an AuditLog row,
    so daily audit-log volume is a free proxy for "is this company still
    being used" — no new instrumentation needed. `last_activity_at` is the
    single figure a super_admin actually scans for ("still operational?").
    """

    points: list[CompanyActivityPoint]
    last_activity_at: Optional[datetime]


class CompanyStatusChangeRequest(BaseModel):
    # CLAUDE.md §6: every suspend/reactivate toggle writes an audit entry with
    # a reason — required, not optional, because suspending a client's whole
    # service is serious and must never be silent.
    reason: str = Field(min_length=1)


class CustomerSignupRequest(BaseModel):
    signup_code: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    # Optional branch code from a branch signup link (/apply/CODE?branch=X).
    # Resolved server-side within the company the signup code names, never
    # trusted as an id (CLAUDE.md rule #3).
    branch_code: Optional[str] = Field(default=None, max_length=32)


class SignupCodeInfoResponse(BaseModel):
    # CLAUDE.md §17/§21: pre-validate a code before the signup form is filled
    # — deliberately nothing beyond name, active status, and cosmetic branding
    # (no id, no signup_code echoed back, nothing that identifies anyone).
    company_name: str
    active: bool
    # Present only when a valid ?branch= code was given.
    branch_name: Optional[str] = None
    logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None
