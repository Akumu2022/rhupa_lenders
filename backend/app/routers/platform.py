"""CLAUDE.md §9: the ONLY place cross-tenant access is allowed, gated on
require_role("super_admin"). super_admin creates companies + seeds their first
system_administrator, and toggles suspend/reactivate — each toggle is a
platform-audited, reasoned action (CLAUDE.md §6).
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..audit import write_audit
from ..company_status_cache import set_cached_status
from ..db import get_session
from ..db_helpers import get_or_404
from ..deps import require_role
from ..loan_seed import seed_default_loan_products
from ..models import AuditAction, AuditLog, Company, CompanyStatus, User, UserRole
from ..schemas.company import (
    CompanyActivityPoint,
    CompanyActivityResponse,
    CompanyCreateRequest,
    CompanyDetailResponse,
    CompanyResponse,
    CompanyStatusChangeRequest,
    CompanyUserCounts,
    CompanyUserRow,
)
from ..schemas.user import PlatformPasswordResetRequest
from ..security import hash_password
from ..signup_code import generate_signup_code
from ..user_stats import compute_user_counts

router = APIRouter(prefix="/platform", tags=["platform"])

_ACTIVITY_TREND_DAYS = 30


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


@router.get("/companies/{company_id}", response_model=CompanyDetailResponse)
def get_company_detail(
    company_id: int,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.super_admin)),
) -> CompanyDetailResponse:
    company = get_or_404(session, Company, company_id, detail="Company not found")
    counts = compute_user_counts(session, company_id=company_id)
    return CompanyDetailResponse(
        **CompanyResponse.model_validate(company).model_dump(),
        users=CompanyUserCounts(
            staff_total=counts.staff_total,
            staff_active=counts.staff_active,
            staff_inactive=counts.staff_inactive,
            customer_total=counts.customer_total,
            customer_active=counts.customer_active,
            customer_inactive=counts.customer_inactive,
        ),
    )


@router.get("/companies/{company_id}/users", response_model=list[CompanyUserRow])
def list_company_users(
    company_id: int,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.super_admin)),
) -> list[CompanyUserRow]:
    get_or_404(session, Company, company_id, detail="Company not found")
    rows = session.exec(select(User).where(User.company_id == company_id).order_by(User.role, User.id)).all()
    return [CompanyUserRow(id=u.id, email=u.email, full_name=u.full_name, role=u.role, is_active=u.is_active) for u in rows]


@router.get("/companies/{company_id}/activity", response_model=CompanyActivityResponse)
def get_company_activity(
    company_id: int,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.super_admin)),
) -> CompanyActivityResponse:
    """CLAUDE.md §12: every privileged action already writes an AuditLog row —
    daily volume over the trailing window is a free "is this company still
    active" signal with no new instrumentation."""
    get_or_404(session, Company, company_id, detail="Company not found")

    today = date.today()
    window_start = today - timedelta(days=_ACTIVITY_TREND_DAYS - 1)
    window_start_dt = datetime.combine(window_start, datetime.min.time(), tzinfo=timezone.utc)

    rows = session.exec(
        select(AuditLog.created_at).where(
            AuditLog.company_id == company_id, AuditLog.created_at >= window_start_dt
        )
    ).all()

    by_day: dict[date, int] = {window_start + timedelta(days=i): 0 for i in range(_ACTIVITY_TREND_DAYS)}
    for created_at in rows:
        day = created_at.date()
        if day in by_day:
            by_day[day] += 1

    last_activity_at = session.exec(
        select(func.max(AuditLog.created_at)).where(AuditLog.company_id == company_id)
    ).one()

    return CompanyActivityResponse(
        points=[CompanyActivityPoint(date=d, audit_log_count=c) for d, c in sorted(by_day.items())],
        last_activity_at=last_activity_at,
    )


@router.post("/users/{user_id}/reset-password", response_model=CompanyUserRow)
def reset_user_password(
    user_id: int,
    body: PlatformPasswordResetRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.super_admin)),
) -> CompanyUserRow:
    """super_admin support action: any user in any company forgot/lost
    access to their password. Cross-tenant by design (this whole router is
    the one deliberate bypass, CLAUDE.md §9) — always reasoned and audited."""
    target = get_or_404(session, User, user_id, detail="User not found")

    target.hashed_password = hash_password(body.new_password)
    session.add(target)
    write_audit(
        session,
        actor=admin,
        action=AuditAction.USER_PASSWORD_RESET.value,
        entity_type="User",
        entity_id=user_id,
        reason=body.reason,
        company_id=target.company_id,
        is_platform_action=True,
    )
    session.commit()
    session.refresh(target)
    return CompanyUserRow(id=target.id, email=target.email, full_name=target.full_name, role=target.role, is_active=target.is_active)


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
