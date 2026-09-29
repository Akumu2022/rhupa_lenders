"""TOTP MFA helpers — CLAUDE.md §4. Pure logic (secret/QR generation,
recovery-code issuance/verification) shared by app/routers/mfa.py and
app/routers/auth.py's login flow; kept separate from the HTTP layer the
same way app/application_review.py and app/loan_calculation.py are.
"""

import base64
import io
import secrets
from datetime import datetime, timezone

import pyotp
import qrcode
from sqlmodel import Session, select

from .models import MfaRecoveryCode, User
from .security import hash_password, verify_password

_ISSUER_NAME = "Rupha Royals"
_RECOVERY_CODE_COUNT = 10


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(*, secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=_ISSUER_NAME)


def qr_code_data_uri(uri: str) -> str:
    img = qrcode.make(uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def verify_totp_code(secret: str, code: str) -> bool:
    # valid_window=1 tolerates one 30s step of clock drift either side —
    # standard TOTP leniency, still a ~90s total window.
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def _generate_recovery_code() -> str:
    # 8 hex chars, grouped for readability — e.g. "a1b2-c3d4".
    raw = secrets.token_hex(4)
    return f"{raw[:4]}-{raw[4:]}"


def issue_recovery_codes(session: Session, *, user: User) -> list[str]:
    """Replaces any existing (unused or used) recovery codes with a fresh
    set of 10 — called once, on /auth/mfa/confirm. Returns the PLAIN codes;
    only their hashes are persisted."""
    existing = session.exec(select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id)).all()
    for row in existing:
        session.delete(row)

    plain_codes = [_generate_recovery_code() for _ in range(_RECOVERY_CODE_COUNT)]
    for code in plain_codes:
        session.add(MfaRecoveryCode(user_id=user.id, company_id=user.company_id, code_hash=hash_password(code)))
    return plain_codes


def consume_recovery_code(session: Session, *, user: User, code: str) -> bool:
    """Single-use: the first unused row whose hash matches is marked used
    and the change is left for the caller to commit alongside everything
    else in that request (same pattern as every other write in this app)."""
    candidates = session.exec(
        select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.used_at.is_(None))
    ).all()
    for candidate in candidates:
        if verify_password(code, candidate.code_hash):
            candidate.used_at = datetime.now(timezone.utc)
            session.add(candidate)
            return True
    return False
