from typing import Optional

from pydantic import BaseModel, Field


class MfaStatusResponse(BaseModel):
    mfa_enabled: bool


class MfaEnrollResponse(BaseModel):
    otpauth_uri: str
    qr_code_data_uri: str


class MfaConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MfaConfirmResponse(BaseModel):
    recovery_codes: list[str]


class MfaDisableRequest(BaseModel):
    password: str
    code: str = Field(min_length=6, max_length=6)


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: Optional[str] = Field(default=None, min_length=6, max_length=6)
    recovery_code: Optional[str] = None
