from typing import Optional

from pydantic import BaseModel, ConfigDict

from ..models import CompanyStatus


class CompanyInfoResponse(BaseModel):
    """Deliberately slimmer than platform.CompanyResponse — no signup_code.
    Every staff/customer role can see their own company's name/status (for the
    top bar); only system_administrator views/regenerates the signup code (§7).
    Branding fields (CLAUDE.md §21) are included — cosmetic, not sensitive —
    so the frontend can theme the shell for whichever company the logged-in
    user belongs to."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: CompanyStatus
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None
    brand_accent_color: Optional[str] = None
    support_email: Optional[str] = None
    support_phone: Optional[str] = None
    address: Optional[str] = None
