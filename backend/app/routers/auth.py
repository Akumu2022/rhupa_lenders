"""CLAUDE.md §4: one users table, one login. The JWT carries both the role and
company_id claims (company_id null for super_admin).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from ..db import get_session
from ..limiter import limiter
from ..models import User
from ..schemas.auth import LoginRequest, TokenResponse
from ..security import create_access_token, verify_password
from ..tenancy import tenant_context

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, body: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    # Email is globally unique and the client already asserts it by typing it
    # in — there is no company to scope by yet at this point, so this is the
    # one other place (besides /platform and scripts/tests) tenant_context(None)
    # is deliberately used: it returns at most one row, never a cross-tenant list.
    with tenant_context(None):
        user = session.exec(select(User).where(User.email == body.email)).first()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    token = create_access_token(user_id=user.id, role=user.role.value, company_id=user.company_id)
    return TokenResponse(access_token=token, role=user.role.value, company_id=user.company_id)
