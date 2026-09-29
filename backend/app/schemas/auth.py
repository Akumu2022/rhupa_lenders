from typing import Literal, Optional

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    company_id: Optional[int]


class MfaRequiredResponse(BaseModel):
    """CLAUDE.md §4/MFA: returned by POST /auth/login instead of a
    TokenResponse when the account has MFA enabled — the frontend then
    collects a code and calls POST /auth/mfa/verify with `mfa_token`."""

    mfa_required: Literal[True] = True
    mfa_token: str
