from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from ..models import KYCStatus


class KYCVerifyRequest(BaseModel):
    notes: Optional[str] = None


class KYCRejectRequest(BaseModel):
    # CLAUDE.md §10: on rejection the ball goes back to the customer with the
    # reason — it is never optional here, unlike on verify.
    reason: str = Field(min_length=1)


class ComplianceProfileResponse(BaseModel):
    id: int
    user_id: int
    kyc_status: KYCStatus
    date_of_birth: date
    national_id_number: str
    phone_number: str
    residential_address: str
    employment_status: str
    monthly_income: Decimal
    occupation: str
    has_id_document_back: bool
    has_selfie: bool
    created_at: datetime
    reviewed_by: Optional[int]
    reviewed_at: Optional[datetime]
    review_notes: Optional[str]
    customer_full_name: str
    customer_email: str

    # CLAUDE.md §27 (M11): extended registration fields — optional since a
    # pre-M11 or self-signup profile may not have filled all of these in.
    customer_number: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    id_type: Optional[str] = None
    gender: Optional[str] = None
    nationality: Optional[str] = None
    marital_status: Optional[str] = None
    dependants_count: Optional[int] = None
    phone_number_alt: Optional[str] = None
    next_of_kin_name: Optional[str] = None
    next_of_kin_relationship: Optional[str] = None
    next_of_kin_phone: Optional[str] = None
