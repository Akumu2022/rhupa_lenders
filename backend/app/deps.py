"""The central auth/tenancy/suspension gate (CLAUDE.md §4, §5, §6, §15).

`get_current_user` is the ONE place every authenticated request passes through:
it decodes the JWT, enters `tenant_context(company_id)` for the lifetime of the
request (so every downstream query is automatically scoped — see tenancy.py),
and checks `User.is_active` and `Company.status` before the route body ever
runs. Routes never re-implement any part of this.
"""

from typing import Iterator, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from .company_status_cache import get_cached_status, set_cached_status
from .db import get_session
from .models import Company, CompanyStatus, User, UserRole
from .security import decode_access_token
from .tenancy import tenant_context

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# CLAUDE.md §6 allow-list: (path template, HTTP method) pairs exempt from the
# suspension check. Repayment stays open so a suspended company's borrowers
# can still pay down what they owe (rule #10) — disbursement is deliberately
# NOT here ("new applications / disbursements: stopped").
SUSPENSION_ALLOWLIST: set[tuple[str, str]] = {
    ("/loans/{loan_id}/repay", "POST"),
}

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _company_status(session: Session, company_id: int) -> Optional[CompanyStatus]:
    cached = get_cached_status(company_id)
    if cached is not None:
        return cached
    fetched = session.exec(select(Company.status).where(Company.id == company_id)).first()
    if fetched is not None:
        set_cached_status(company_id, fetched)
    return fetched


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> Iterator[User]:
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise _CREDENTIALS_EXCEPTION

    # Entered for the whole request via this generator dependency (same pattern
    # as get_session) so every query any route makes downstream is scoped.
    with tenant_context(payload.company_id):
        user = session.get(User, payload.user_id)
        if user is None or user.role.value != payload.role:
            raise _CREDENTIALS_EXCEPTION

        # CLAUDE.md §15: checked every request, in the same central gate as
        # company suspension — a deactivated staff account loses access
        # immediately, not merely once its JWT expires.
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

        # super_admin has company_id = None and is exempt (CLAUDE.md §5, §6).
        if user.company_id is not None:
            company_status = _company_status(session, user.company_id)
            if company_status == CompanyStatus.suspended:
                route = request.scope.get("route")
                route_key = (getattr(route, "path", request.url.path), request.method)
                if route_key not in SUSPENSION_ALLOWLIST:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "code": "company_suspended",
                            "message": "This company's account is suspended.",
                        },
                    )

        yield user


def require_role(*roles: UserRole):
    allowed = {role.value for role in roles}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
        return user

    return dependency
