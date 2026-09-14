from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field

from ..models import KYCStatus


class ProfileSubmitForm(BaseModel):
    # Must be the ONLY body parameter on the route (files included) — FastAPI
    # only flattens a Form(model)'s fields into top-level multipart fields
    # when it's the sole body param; mixing it with separate File() params
    # forces "embedded" mode and breaks the flattening.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    date_of_birth: date
    national_id_number: str = Field(min_length=1)
    phone_number: str = Field(min_length=1)
    residential_address: str = Field(min_length=1)
    employment_status: str = Field(min_length=1)
    monthly_income: Decimal = Field(gt=0)
    occupation: str = Field(min_length=1)
    id_document: UploadFile  # ID front
    id_document_back: UploadFile
    selfie_photo: Optional[UploadFile] = None

    # CLAUDE.md §27 (M11): optional here — a self-signup customer may fill
    # these in, but the original 7 fields above stay the only required ones
    # for this endpoint. The credit-officer registration endpoint
    # (app/routers/customers.py) requires the fuller set at its own schema.
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


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kyc_status: KYCStatus
    date_of_birth: date
    national_id_number: str
    phone_number: str
    residential_address: str
    employment_status: str
    monthly_income: Decimal
    occupation: str
    # CLAUDE.md §9: rejection reason is fine to show the customer; reviewer
    # identity is not — `reviewed_by` is deliberately omitted here.
    review_notes: Optional[str]
    reviewed_at: Optional[datetime]

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
