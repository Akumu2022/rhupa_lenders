"""CLAUDE.md §27 (M11): the credit-officer-driven registration path — an
officer captures a new customer's full intake (account + KYC profile +
business assessment + referees) in one in-branch flow, alongside the
self-signup path (app/routers/signup.py + app/routers/profile.py) that
stays unchanged. Structurally the same pattern as app/routers/staff.py
(a privileged actor creates a User with role/company_id/branch_id derived
server-side) — just role=customer, with an inline Profile.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..audit import write_audit
from ..customer_registration import compute_business_figures, next_customer_number
from ..db import get_session
from ..deps import require_role
from ..kyc_storage import save_kyc_document
from ..models import AuditAction, BusinessAssessment, Company, KYCStatus, LoanApplication, Profile, Referee, User, UserRole
from ..schemas.compliance import ComplianceProfileResponse
from ..schemas.customers import (
    AssignOfficerRequest,
    BusinessAssessmentRequest,
    BusinessAssessmentResponse,
    CustomerRegisterForm,
    CustomerResponse,
    RefereeInput,
    RefereeResponse,
)
from ..schemas.loan import LoanApplicationResponse
from ..security import hash_password
from .compliance import _to_response as _profile_to_response

router = APIRouter(prefix="/customers", tags=["customers"])

_VIEW_ROLES = (UserRole.credit_officer, UserRole.branch_manager, UserRole.system_administrator)


def _customer_response(customer: User, profile: Profile, officer_names: dict[int, str] | None = None) -> CustomerResponse:
    return CustomerResponse(
        id=customer.id,
        profile_id=profile.id,
        customer_number=profile.customer_number,
        full_name=customer.full_name,
        email=customer.email,
        branch_id=customer.branch_id,
        kyc_status=profile.kyc_status,
        created_at=profile.created_at,
        assigned_officer_id=customer.assigned_officer_id,
        assigned_officer_name=(officer_names or {}).get(customer.assigned_officer_id) if customer.assigned_officer_id else None,
    )


def _officer_names(session: Session, officer_ids: set[int]) -> dict[int, str]:
    if not officer_ids:
        return {}
    return {u.id: u.full_name for u in session.exec(select(User).where(User.id.in_(officer_ids))).all()}


def _get_existing_business_assessment(session: Session, profile_id: int) -> BusinessAssessment | None:
    return session.exec(select(BusinessAssessment).where(BusinessAssessment.profile_id == profile_id)).first()


def _get_customer_profile(session: Session, customer_id: int) -> tuple[User, Profile]:
    # session.get is tenant-scoped — a customer_id from another company
    # comes back None here, indistinguishable from "doesn't exist" (§5).
    customer = session.get(User, customer_id)
    if customer is None or customer.role != UserRole.customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    profile = session.exec(select(Profile).where(Profile.user_id == customer_id)).first()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer has no profile yet")
    return customer, profile


@router.get("", response_model=list[CustomerResponse])
def list_customers(
    mine: bool = False,
    session: Session = Depends(get_session),
    staff: User = Depends(require_role(*_VIEW_ROLES)),
) -> list[CustomerResponse]:
    """CLAUDE.md §5/§25: credit_officer/branch_manager see only their own
    branch's customers — a hand-filtered branch_id query, never a
    company_id one (that stays automatic). system_administrator sees the
    whole company. Only customers with a submitted profile appear (a
    self-signed-up customer who hasn't submitted KYC yet has no
    customer_number/kyc_status to show)."""
    query = select(User, Profile).join(Profile, Profile.user_id == User.id).where(User.role == UserRole.customer)
    if staff.role in (UserRole.credit_officer, UserRole.branch_manager):
        query = query.where(User.branch_id == staff.branch_id)
    if mine and staff.role == UserRole.credit_officer:
        query = query.where(User.assigned_officer_id == staff.id)
    rows = session.exec(query.order_by(User.id)).all()
    names = _officer_names(session, {c.assigned_officer_id for c, _ in rows if c.assigned_officer_id})
    return [_customer_response(customer, profile, names) for customer, profile in rows]


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def register_customer(
    form_data: Annotated[CustomerRegisterForm, Form()],
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.credit_officer)),
) -> CustomerResponse:
    customer = User(
        email=form_data.email,
        hashed_password=hash_password(form_data.password),
        role=UserRole.customer,  # hardcoded — never from the request body
        full_name=form_data.full_name,
        company_id=officer.company_id,  # inherited — never from the request body
        branch_id=officer.branch_id,  # inherited — never from the request body
        assigned_officer_id=officer.id,  # the registering officer owns the customer
        is_active=True,
    )
    session.add(customer)
    try:
        session.flush()  # assigns customer.id without committing yet
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    try:
        id_document_path = await save_kyc_document(
            officer.company_id, customer.id, form_data.id_document, field_name="id_document"
        )
        id_document_back_path = await save_kyc_document(
            officer.company_id, customer.id, form_data.id_document_back, field_name="id_document_back"
        )
        selfie_path = (
            await save_kyc_document(officer.company_id, customer.id, form_data.selfie_photo, field_name="selfie_photo")
            if form_data.selfie_photo is not None
            else None
        )
    except ValueError as exc:
        session.rollback()  # discards the flushed-but-uncommitted User row too
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    company = session.get(Company, officer.company_id)
    customer_number = next_customer_number(session, company)

    profile = Profile(
        user_id=customer.id,
        company_id=officer.company_id,
        date_of_birth=form_data.date_of_birth,
        national_id_number=form_data.national_id_number,
        phone_number=form_data.phone_number,
        residential_address=form_data.residential_address,
        employment_status=form_data.employment_status,
        monthly_income=form_data.monthly_income,
        occupation=form_data.occupation,
        id_document_path=id_document_path,
        id_document_back_path=id_document_back_path,
        selfie_path=selfie_path,
        kyc_status=KYCStatus.pending,
        customer_number=customer_number,
        first_name=form_data.first_name,
        middle_name=form_data.middle_name,
        last_name=form_data.last_name,
        id_type=form_data.id_type,
        gender=form_data.gender,
        nationality=form_data.nationality,
        marital_status=form_data.marital_status,
        dependants_count=form_data.dependants_count,
        phone_number_alt=form_data.phone_number_alt,
        next_of_kin_name=form_data.next_of_kin_name,
        next_of_kin_relationship=form_data.next_of_kin_relationship,
        next_of_kin_phone=form_data.next_of_kin_phone,
    )
    session.add(profile)

    write_audit(
        session,
        actor=officer,
        action=AuditAction.CUSTOMER_REGISTER.value,
        entity_type="User",
        entity_id=customer.id,
        reason=f"customer_number={customer_number}",
        company_id=officer.company_id,
    )
    session.commit()
    session.refresh(customer)
    session.refresh(profile)
    return _customer_response(customer, profile, {officer.id: officer.full_name})


@router.get("/{customer_id}", response_model=ComplianceProfileResponse)
def get_customer_detail(
    customer_id: int,
    session: Session = Depends(get_session),
    staff: User = Depends(require_role(*_VIEW_ROLES)),
) -> ComplianceProfileResponse:
    customer, profile = _get_customer_profile(session, customer_id)
    return _profile_to_response(profile, customer)


@router.get("/{customer_id}/applications", response_model=list[LoanApplicationResponse])
def list_customer_applications(
    customer_id: int,
    session: Session = Depends(get_session),
    staff: User = Depends(require_role(*_VIEW_ROLES)),
) -> list[LoanApplication]:
    """Backs the shared customer-profile page's Applications section (visible
    to all three viewer roles, read-only) and the credit officer's
    pending-application check before offering to apply on this customer's
    behalf. CLAUDE.md §25: credit_officer/branch_manager stay within their
    own branch — same scope as `GET /customers` — system_administrator sees
    any customer in the company (tenant scope already covers that)."""
    customer, _ = _get_customer_profile(session, customer_id)
    if staff.role in (UserRole.credit_officer, UserRole.branch_manager) and customer.branch_id != staff.branch_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return list(
        session.exec(
            select(LoanApplication)
            .where(LoanApplication.customer_id == customer_id)
            .order_by(LoanApplication.created_at.desc())
        ).all()
    )


@router.get("/{customer_id}/business-assessment", response_model=BusinessAssessmentResponse)
def get_business_assessment(
    customer_id: int,
    session: Session = Depends(get_session),
    staff: User = Depends(require_role(*_VIEW_ROLES)),
) -> BusinessAssessment:
    _, profile = _get_customer_profile(session, customer_id)
    assessment = session.exec(
        select(BusinessAssessment).where(BusinessAssessment.profile_id == profile.id)
    ).first()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No business assessment captured yet")
    return assessment


@router.patch("/{customer_id}/business-assessment", response_model=BusinessAssessmentResponse)
def upsert_business_assessment(
    customer_id: int,
    body: BusinessAssessmentRequest,
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.credit_officer)),
) -> BusinessAssessment:
    """CLAUDE.md §27: one row per profile — create on first call, update on
    every later call. net_income/debt_service_capacity are ALWAYS
    recomputed server-side here; the request body has no such fields."""
    _, profile = _get_customer_profile(session, customer_id)
    net_income, debt_service_capacity = compute_business_figures(
        total_income=body.total_income,
        total_expenses=body.total_expenses,
        existing_debt_obligations=body.existing_debt_obligations,
    )

    existing = _get_existing_business_assessment(session, profile.id)

    if existing is not None:
        for field, value in body.model_dump().items():
            setattr(existing, field, value)
        existing.net_income = net_income
        existing.debt_service_capacity = debt_service_capacity
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        assessment = existing
        action = AuditAction.BUSINESS_ASSESSMENT_UPDATE.value
    else:
        assessment = BusinessAssessment(
            profile_id=profile.id,
            company_id=profile.company_id,
            created_by=officer.id,
            net_income=net_income,
            debt_service_capacity=debt_service_capacity,
            **body.model_dump(),
        )
        session.add(assessment)
        action = AuditAction.BUSINESS_ASSESSMENT_CREATE.value

    try:
        session.flush()  # assigns assessment.id for the audit entry below
    except IntegrityError:
        # BusinessAssessment.profile_id is unique — this fires if a
        # concurrent request's create won the race between this request's
        # `existing is None` check above and this flush (CLAUDE.md §5/§14
        # fail-closed discipline: a double-click or retried request must
        # get a clean 409, never an unhandled 500).
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Business assessment already exists for this customer",
        )
    write_audit(
        session,
        actor=officer,
        action=action,
        entity_type="BusinessAssessment",
        entity_id=assessment.id,
        company_id=officer.company_id,
    )
    session.commit()
    session.refresh(assessment)
    return assessment


@router.get("/{customer_id}/referees", response_model=list[RefereeResponse])
def list_referees(
    customer_id: int,
    session: Session = Depends(get_session),
    staff: User = Depends(require_role(*_VIEW_ROLES)),
) -> list[Referee]:
    _, profile = _get_customer_profile(session, customer_id)
    return list(session.exec(select(Referee).where(Referee.profile_id == profile.id).order_by(Referee.id)).all())


@router.post("/{customer_id}/referees", response_model=RefereeResponse, status_code=status.HTTP_201_CREATED)
def add_referee(
    customer_id: int,
    body: RefereeInput,
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.credit_officer)),
) -> Referee:
    _, profile = _get_customer_profile(session, customer_id)
    referee = Referee(profile_id=profile.id, company_id=profile.company_id, **body.model_dump())
    session.add(referee)
    session.flush()  # assigns referee.id for the audit entry below

    write_audit(
        session,
        actor=officer,
        action=AuditAction.REFEREE_ADD.value,
        entity_type="Referee",
        entity_id=referee.id,
        reason=body.full_name,
        company_id=officer.company_id,
    )
    session.commit()
    session.refresh(referee)
    return referee


@router.patch("/{customer_id}/officer", response_model=CustomerResponse)
def assign_customer_officer(
    customer_id: int,
    body: AssignOfficerRequest,
    session: Session = Depends(get_session),
    staff: User = Depends(require_role(UserRole.branch_manager, UserRole.system_administrator)),
) -> CustomerResponse:
    """Hand a customer to a (different) credit officer. Branch managers only
    within their own branch; the system administrator anywhere in the
    company. The officer must be an active credit officer in the customer's
    own branch, so a customer can never be owned across branches."""
    customer, profile = _get_customer_profile(session, customer_id)
    if staff.role == UserRole.branch_manager and customer.branch_id != staff.branch_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    officer = None
    if body.officer_id is not None:
        if customer.branch_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assign the customer to a branch first")
        # session.get is tenant-scoped (CLAUDE.md §5).
        officer = session.get(User, body.officer_id)
        if (
            officer is None
            or officer.role != UserRole.credit_officer
            or not officer.is_active
            or officer.branch_id != customer.branch_id
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Choose an active credit officer in the customer's branch",
            )

    previous = customer.assigned_officer_id
    if previous == body.officer_id:
        return _customer_response(customer, profile, _officer_names(session, {previous} if previous else set()))

    # CLAUDE.md §14: compare-and-set on the value we read.
    unchanged = User.assigned_officer_id.is_(None) if previous is None else User.assigned_officer_id == previous
    result = session.execute(
        update(User).where(User.id == customer.id, unchanged).values(assigned_officer_id=body.officer_id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The officer was changed by someone else, reload and retry")

    write_audit(
        session,
        actor=staff,
        action=AuditAction.CUSTOMER_OFFICER_ASSIGN.value,
        entity_type="User",
        entity_id=customer.id,
        reason=f"officer {previous or 'none'} -> {body.officer_id or 'none'}",
        company_id=staff.company_id,
    )
    session.commit()
    session.refresh(customer)
    names = {officer.id: officer.full_name} if officer else {}
    return _customer_response(customer, profile, names)
