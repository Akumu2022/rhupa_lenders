"""CLAUDE.md §7: customer self-registration via company signup code. The
client presents a code, never a company_id — the server resolves code ->
company and stamps company_id; role is hardcoded to customer. Rate-limited
(§2) so codes can't be brute-forced even at >=10 chars of entropy.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..db import get_session
from ..limiter import limiter
from ..models import Company, CompanyStatus, User, UserRole
from ..schemas.company import CustomerSignupRequest, SignupCodeInfoResponse
from ..schemas.auth import TokenResponse
from ..security import create_access_token, hash_password
from ..tenancy import tenant_context

router = APIRouter(prefix="/signup", tags=["signup"])


@router.get("/resolve/{code}", response_model=SignupCodeInfoResponse)
@limiter.limit("10/minute")
def resolve_signup_code(
    request: Request,
    code: str,
    session: Session = Depends(get_session),
) -> SignupCodeInfoResponse:
    """CLAUDE.md §17: lets the frontend show "Create your account with
    Company X" (or reject a dead link) before the customer fills the form.
    Unauthenticated and code-guessable like POST /signup itself, so it gets
    the same rate limit (§2) — entropy is the first layer, this is the second.
    """
    company = session.exec(select(Company).where(Company.signup_code == code)).first()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired signup link")
    return SignupCodeInfoResponse(
        company_name=company.name,
        active=company.status == CompanyStatus.active,
        logo_url=company.logo_url,
        brand_primary_color=company.brand_primary_color,
    )


@router.post("", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def customer_signup(
    request: Request,
    body: CustomerSignupRequest,
    session: Session = Depends(get_session),
) -> TokenResponse:
    company = session.exec(select(Company).where(Company.signup_code == body.signup_code)).first()
    if company is None:
        # Never reveal whether a code is malformed vs. simply unknown.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid company code")

    if company.status != CompanyStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This company is not currently accepting new signups",
        )

    # Global email-uniqueness pre-check, same rationale as /auth/login: no
    # company scope is known yet, and the unique index guarantees at most one
    # row comes back — not a cross-tenant listing.
    with tenant_context(None):
        existing = session.exec(select(User).where(User.email == body.email)).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    customer = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        role=UserRole.customer,  # hardcoded — never from the request body
        full_name=body.full_name,
        company_id=company.id,  # resolved from the code — never from the request body
        is_active=True,
    )
    # No auth dependency ran for this unauthenticated route, so no tenant scope
    # is set yet — enter it explicitly for the new customer's own company so
    # the post-commit refresh (a SELECT against a TenantMixin model) doesn't
    # trip the fail-closed guard.
    with tenant_context(company.id):
        session.add(customer)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
        session.refresh(customer)

    token = create_access_token(user_id=customer.id, role=customer.role.value, company_id=customer.company_id)
    return TokenResponse(access_token=token, role=customer.role.value, company_id=customer.company_id)
