import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from ..models import CompanyStatus

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


class SignupCodeInfoResponse(BaseModel):
    # CLAUDE.md §17/§21: pre-validate a code before the signup form is filled
    # — deliberately nothing beyond name, active status, and cosmetic branding
    # (no id, no signup_code echoed back, nothing that identifies anyone).
    company_name: str
    active: bool
    logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None
