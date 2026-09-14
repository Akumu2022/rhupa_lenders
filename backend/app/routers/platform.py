"""CLAUDE.md §9: the ONLY place cross-tenant access is allowed, gated on
require_role("super_admin"). super_admin creates companies + seeds their first
system_administrator, and toggles suspend/reactivate — each toggle is a
platform-audited, reasoned action (CLAUDE.md §6).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..audit import write_audit
from ..company_status_cache import set_cached_status
from ..db import get_session
from ..deps import require_role
from ..loan_seed import seed_default_loan_products
from ..models import AuditAction, Company, CompanyStatus, User, UserRole
from ..schemas.company import CompanyCreateRequest, CompanyResponse, CompanyStatusChangeRequest
from ..security import hash_password
from ..signup_code import generate_signup_code

router = APIRouter(prefix="/platform", tags=["platform"])


@router.post("/companies", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyCreateRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.super_admin)),
) -> Company:
    company = Company(
        name=body.name,
        signup_code=generate_signup_code(),
        legal_name=body.legal_name,
        tagline=body.tagline,
        logo_url=body.logo_url,
        brand_primary_color=body.brand_primary_color,
        brand_accent_color=body.brand_accent_color,
        support_email=body.support_email,
        support_phone=body.support_phone,
        address=body.address,
        registration_number=body.registration_number,
    )
    session.add(company)
    try:
        session.flush()  # assigns company.id without committing yet
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Signup code collision, retry")

    system_administrator = User(
        email=body.admin_email,
        hashed_password=hash_password(body.admin_password),
        role=UserRole.system_administrator,
        full_name=body.admin_full_name,
        company_id=company.id,
        is_active=True,
    )
    session.add(system_administrator)

    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin email already in use")

    # CLAUDE.md M4: every company starts with a fixed default catalog.
    seed_default_loan_products(session, company.id)

    write_audit(
        session,
        actor=admin,
        action=AuditAction.COMPANY_CREATE.value,
        entity_type="Company",
        entity_id=company.id,
        reason=f"Seeded first system_administrator: {body.admin_email}",
        company_id=company.id,
        is_platform_action=True,
    )
    session.commit()
    session.refresh(company)
    return company


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.super_admin)),
) -> list[Company]:
    return list(session.exec(select(Company)).all())


def _transition_company_status(
    *,
    session: Session,
    admin: User,
    company_id: int,
    expected: CompanyStatus,
    new_status: CompanyStatus,
    action: str,
    reason: str,
) -> Company:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    # CLAUDE.md §14: compare-and-set, never a blind UPDATE — safe against a
    # doubled click or two admins toggling the same company concurrently.
    result = session.execute(
        update(Company)
        .where(Company.id == company_id, Company.status == expected)
        .values(status=new_status)
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Company is not currently {expected.value}",
        )

    write_audit(
        session,
        actor=admin,
        action=action,
        entity_type="Company",
        entity_id=company_id,
        reason=reason,
        company_id=company_id,
        is_platform_action=True,
    )
    session.commit()
    set_cached_status(company_id, new_status)
    session.refresh(company)
    return company


@router.post("/companies/{company_id}/suspend", response_model=CompanyResponse)
def suspend_company(
    company_id: int,
    body: CompanyStatusChangeRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.super_admin)),
) -> Company:
    return _transition_company_status(
        session=session,
        admin=admin,
        company_id=company_id,
        expected=CompanyStatus.active,
        new_status=CompanyStatus.suspended,
        action=AuditAction.COMPANY_SUSPEND.value,
        reason=body.reason,
    )


@router.post("/companies/{company_id}/reactivate", response_model=CompanyResponse)
def reactivate_company(
    company_id: int,
    body: CompanyStatusChangeRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.super_admin)),
) -> Company:
    return _transition_company_status(
        session=session,
        admin=admin,
        company_id=company_id,
        expected=CompanyStatus.suspended,
        new_status=CompanyStatus.active,
        action=AuditAction.COMPANY_REACTIVATE.value,
        reason=body.reason,
    )
