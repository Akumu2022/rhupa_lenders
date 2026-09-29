"""Password hashing and JWT issuance/verification (CLAUDE.md §2, §4).

Access tokens carry the role and company_id claims and are short-lived; there is
no refresh-token flow in the MVP (see CLAUDE.md §2 for the rationale).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


class TokenPayload:
    def __init__(self, user_id: int, role: str, company_id: Optional[int]):
        self.user_id = user_id
        self.role = role
        self.company_id = company_id


def create_access_token(*, user_id: int, role: str, company_id: Optional[int]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "company_id": company_id,
        # CLAUDE.md §4/MFA: explicit purpose claim so an mfa_pending token
        # (see create_mfa_pending_token below) can never be mistaken for a
        # real access token by get_current_user, even though both are signed
        # with the same key. Tokens issued before this claim existed have no
        # "purpose" at all — decode_access_token below treats that as
        # "access" too, since those are all short-lived (30-60 min) and
        # naturally age out.
        "purpose": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc

    if payload.get("purpose", "access") != "access":
        raise ValueError("Wrong token type")

    user_id = payload.get("sub")
    role = payload.get("role")
    if user_id is None or role is None:
        raise ValueError("Malformed token payload")

    return TokenPayload(user_id=int(user_id), role=role, company_id=payload.get("company_id"))


# CLAUDE.md §4/MFA: a short-lived intermediate token — proves the password
# step already succeeded, but grants no API access on its own (get_current_user
# rejects it via the purpose check above). Only /auth/mfa/verify accepts it.
_MFA_PENDING_EXPIRE_MINUTES = 5


def create_mfa_pending_token(*, user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_MFA_PENDING_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "purpose": "mfa_pending", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_mfa_pending_token(token: str) -> int:
    """Returns the user_id, or raises ValueError."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc

    if payload.get("purpose") != "mfa_pending":
        raise ValueError("Wrong token type")
    user_id = payload.get("sub")
    if user_id is None:
        raise ValueError("Malformed token payload")
    return int(user_id)
