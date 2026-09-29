from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ..models import GuarantorVerificationStatus


class GuarantorRequest(BaseModel):
    full_name: str = Field(min_length=1)
    id_number: str = Field(min_length=1)
    phone_number: str = Field(min_length=1)
    occupation: Optional[str] = None
    residence: Optional[str] = None
    relationship: Optional[str] = None
    guaranteed_amount: Decimal = Field(gt=0)
    consent: bool = False


class GuarantorVerifyRequest(BaseModel):
    verification_status: GuarantorVerificationStatus


class GuarantorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    full_name: str
    id_number: str
    phone_number: str
    occupation: Optional[str]
    residence: Optional[str]
    relationship: Optional[str]
    guaranteed_amount: Decimal
    consent: bool
    verification_status: GuarantorVerificationStatus
    verified_by: Optional[int]
    verified_at: Optional[datetime]
    created_at: datetime


class SecurityRequest(BaseModel):
    description: str = Field(min_length=1)
    estimated_value: Decimal = Field(gt=0)


class SecurityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    description: str
    estimated_value: Decimal
    document_path: Optional[str]
    created_at: datetime
