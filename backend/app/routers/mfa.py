"""CLAUDE.md §4: TOTP MFA for staff roles. Enrollment/confirm/disable are
authenticated (the user acting on their own account); /verify is the
second step of login, gated by a short-lived mfa_pending token instead of
a normal bearer token (get_current_user rejects that token type outright —
see app/security.py), and rate-limited the same as /auth/login since it's
an unauthenticated, guessable-code endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from ..audit import write_audit
from ..db import get_session
from ..deps import get_current_user
from ..limiter import limiter
from ..mfa import (
    consume_recovery_code,
    generate_totp_secret,
    issue_recovery_codes,
    provisioning_uri,
    qr_code_data_uri,
    verify_totp_code,
)
from ..models import AuditAction, User, UserRole
from ..schemas.auth import TokenResponse
from ..schemas.mfa import (
    MfaConfirmRequest,
    MfaConfirmResponse,
    MfaDisableRequest,
    MfaEnrollResponse,
    MfaStatusResponse,
    MfaVerifyRequest,
)
from ..security import create_access_token, decode_mfa_pending_token, verify_password
from ..tenancy import tenant_context

router = APIRouter(prefix="/auth/mfa", tags=["mfa"])

# CLAUDE.md §4: MFA is for staff roles — customers are never required (or
# able) to enroll.
_STAFF_ROLES = tuple(role for role in UserRole if role != UserRole.customer)


@router.get("/status", response_model=MfaStatusResponse)
def get_mfa_status(user: User = Depends(get_current_user)) -> MfaStatusResponse:
    return MfaStatusResponse(mfa_enabled=user.mfa_enabled)


@router.post("/enroll", response_model=MfaEnrollResponse)
def enroll(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MfaEnrollResponse:
    if user.role not in _STAFF_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA is only available to staff accounts")

    # Generates (or regenerates, if the user abandoned a prior enrollment
    # before confirming) a pending secret — not active until /confirm.
    secret = generate_totp_secret()
    user.mfa_secret = secret
    session.add(user)
    session.commit()

    uri = provisioning_uri(secret=secret, email=user.email)
    return MfaEnrollResponse(otpauth_uri=uri, qr_code_data_uri=qr_code_data_uri(uri))


@router.post("/confirm", response_model=MfaConfirmResponse)
def confirm(
    body: MfaConfirmRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MfaConfirmResponse:
    if not user.mfa_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No MFA enrollment in progress")
    if not verify_totp_code(user.mfa_secret, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect code")

    user.mfa_enabled = True
    session.add(user)
    recovery_codes = issue_recovery_codes(session, user=user)

    write_audit(
        session,
        actor=user,
        action=AuditAction.MFA_ENABLE.value,
        entity_type="User",
        entity_id=user.id,
        company_id=user.company_id,
    )
    session.commit()
    return MfaConfirmResponse(recovery_codes=recovery_codes)


@router.post("/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable(
    body: MfaDisableRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    if not user.mfa_enabled or not user.mfa_secret or not verify_totp_code(user.mfa_secret, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect code")

    user.mfa_enabled = False
    user.mfa_secret = None
    session.add(user)

    # Leftover recovery-code rows are inert once mfa_enabled is False
    # (verify() only ever consumes one after checking mfa_enabled) — the
    # next /confirm on re-enrollment replaces them via issue_recovery_codes.
    write_audit(
        session,
        actor=user,
        action=AuditAction.MFA_DISABLE.value,
        entity_type="User",
        entity_id=user.id,
        company_id=user.company_id,
    )
    session.commit()


@router.post("/verify", response_model=TokenResponse)
@limiter.limit("10/minute")
def verify(request: Request, body: MfaVerifyRequest, session: Session = Depends(get_session)) -> TokenResponse:
    try:
        user_id = decode_mfa_pending_token(body.mfa_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired MFA session")

    # Same tenant_context(None) bypass as /auth/login — we don't yet know
    # the caller's company_id (that's what we're about to look up).
    with tenant_context(None):
        user = session.get(User, user_id)

    if user is None or not user.is_active or not user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired MFA session")

    # Everything below (including the final commit, which expires `user`'s
    # loaded attributes) stays inside this user's tenant scope — a fresh
    # attribute load after commit must not fall outside tenant_context and
    # trip the fail-closed guard in app/tenancy.py.
    with tenant_context(user.company_id):
        ok = False
        if body.code and user.mfa_secret and verify_totp_code(user.mfa_secret, body.code):
            ok = True
        elif body.recovery_code:
            ok = consume_recovery_code(session, user=user, code=body.recovery_code)

        if not ok:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect code")

        session.commit()  # persists a consumed recovery code's used_at, if that path was taken
        token = create_access_token(user_id=user.id, role=user.role.value, company_id=user.company_id)
        return TokenResponse(access_token=token, role=user.role.value, company_id=user.company_id)
