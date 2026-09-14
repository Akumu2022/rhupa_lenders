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
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc

    user_id = payload.get("sub")
    role = payload.get("role")
    if user_id is None or role is None:
        raise ValueError("Malformed token payload")

    return TokenPayload(user_id=int(user_id), role=role, company_id=payload.get("company_id"))
