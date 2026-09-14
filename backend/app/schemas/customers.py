from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..models import KYCStatus


class CustomerRegisterForm(BaseModel):
    """CLAUDE.md §27 (M11): the credit-officer-driven registration path —
    unlike the self-signup ProfileSubmitForm, the full client PRD §2A field
    set is required here, since an officer is capturing a complete in-branch
    intake. Must stay the ONLY body parameter on the route (same
    Form()-flattening constraint as ProfileSubmitForm, see its docstring).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # User account fields — same shape self-signup already requires (CLAUDE.md
    # §4: role/company_id/branch_id are still always derived server-side,
    # never from this body).
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)

    # Identity
    first_name: str = Field(min_length=1)
    middle_name: Optional[str] = None
    last_name: str = Field(min_length=1)
    id_type: Literal["national_id", "passport"] = "national_id"
    national_id_number: str = Field(min_length=1)
    date_of_birth: date
    gender: str = Field(min_length=1)
    nationality: str = Field(min_length=1)
    marital_status: str = Field(min_length=1)
    dependants_count: int = Field(ge=0)

    # Contact
    phone_number: str = Field(min_length=1)
    phone_number_alt: Optional[str] = None
    residential_address: str = Field(min_length=1)

    # Employment
    employment_status: str = Field(min_length=1)
    occupation: str = Field(min_length=1)
    monthly_income: Decimal = Field(gt=0)

    # Next of kin (referees are a separate list — see RefereeInput/the
    # POST /customers/{id}/referees endpoint, added after the customer exists)
    next_of_kin_name: str = Field(min_length=1)
    next_of_kin_relationship: str = Field(min_length=1)
    next_of_kin_phone: str = Field(min_length=1)

    # Documents — same handling as ProfileSubmitForm via app/kyc_storage.py.
    id_document: UploadFile
    id_document_back: UploadFile
    selfie_photo: Optional[UploadFile] = None


class CustomerResponse(BaseModel):
    """Summary shape for the registration response and the customer list —
    composed from User + Profile, so built manually in the router rather
    than via from_attributes on a single ORM object."""

    id: int  # User.id
    profile_id: int
    customer_number: Optional[str]
    full_name: str
    email: str
    branch_id: Optional[int]
    kyc_status: KYCStatus
    created_at: datetime


class RefereeInput(BaseModel):
    full_name: str = Field(min_length=1)
    phone_number: str = Field(min_length=1)
    relationship: Optional[str] = None
    address: Optional[str] = None


class RefereeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    full_name: str
    phone_number: str
    relationship: Optional[str]
    address: Optional[str]
    created_at: datetime


class BusinessAssessmentRequest(BaseModel):
    """CLAUDE.md §27: net_income/debt_service_capacity are deliberately NOT
    fields here — app/customer_registration.py::compute_business_figures is
    the only writer of those two, server-side, every time."""

    business_name: str = Field(min_length=1)
    business_type: str = Field(min_length=1)
    ownership: str = Field(min_length=1)
    physical_location: str = Field(min_length=1)
    years_in_operation: int = Field(ge=0)
    sales_frequency: Literal["daily", "weekly", "monthly"]
    total_income: Decimal = Field(ge=0)
    total_expenses: Decimal = Field(ge=0)
    reported_profit: Optional[Decimal] = None
    stock_value: Optional[Decimal] = None
    existing_loans_amount: Optional[Decimal] = None
    other_lenders: Optional[str] = None
    bank_mpesa_turnover: Optional[Decimal] = None
    business_assets_value: Optional[Decimal] = None
    cash_flow_notes: Optional[str] = None
    existing_debt_obligations: Decimal = Field(default=Decimal("0.00"), ge=0)


class BusinessAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    business_name: str
    business_type: str
    ownership: str
    physical_location: str
    years_in_operation: int
    sales_frequency: str
    total_income: Decimal
    total_expenses: Decimal
    reported_profit: Optional[Decimal]
    stock_value: Optional[Decimal]
    existing_loans_amount: Optional[Decimal]
    other_lenders: Optional[str]
    bank_mpesa_turnover: Optional[Decimal]
    business_assets_value: Optional[Decimal]
    cash_flow_notes: Optional[str]
    existing_debt_obligations: Decimal
    net_income: Decimal
    debt_service_capacity: Decimal
    created_at: datetime
    updated_at: datetime
