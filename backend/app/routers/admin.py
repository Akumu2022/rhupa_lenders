"""CLAUDE.md §9/M8: system_administrator's company-wide oversight surface — "their
audit log" is the first piece; applications/KYC/loans/products/portfolio
oversight land here too as they ship.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..audit import write_audit
from ..db import get_session
from ..db_helpers import get_or_404
from ..deps import require_role
from ..loan_delinquency import sync_loan_delinquency
from ..portfolio import compute_portfolio_summary, compute_portfolio_trend
from ..models import (
    ApplicationStatus,
    AuditAction,
    AuditLog,
    Branch,
    InterestModel,
    KYCStatus,
    Loan,
    LoanApplication,
    LoanProduct,
    LoanStatus,
    Profile,
    User,
    UserRole,
)
from ..schemas.admin import (
    AdminLoanProductResponse,
    AdminLoanResponse,
    ApplicationOverrideRequest,
    AuditLogResponse,
    BranchCreateRequest,
    BranchResponse,
    BranchUpdateRequest,
    KYCOverrideRequest,
    LoanProductUpdateRequest,
    PortfolioSummaryResponse,
    PortfolioTrendPoint,
    PortfolioTrendResponse,
)
from ..schemas.compliance import ComplianceProfileResponse
from ..schemas.credit import CreditApplicationResponse, LoanApprovalResponse, LoanResponse
from .compliance import _to_response as _profile_to_response
from .credit import _row_to_response as _application_row_to_response
from .credit import _to_response as _application_to_response
from .credit import create_loan_for_application

router = APIRouter(prefix="/admin", tags=["admin"])

# MVP simplification: no server-side pagination yet — a real deployment with
# heavy audit volume would need it, but the DataTable component paginates
# client-side and this caps the payload in the meantime.
_AUDIT_LOG_LIMIT = 500


@router.get("/audit-log", response_model=list[AuditLogResponse])
def get_audit_log(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> list[AuditLog]:
    return list(
        session.exec(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(_AUDIT_LOG_LIMIT)
        ).all()
    )


@router.get("/branches", response_model=list[BranchResponse])
def list_branches(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> list[Branch]:
    return list(session.exec(select(Branch).order_by(Branch.id)).all())


def _check_manager_id(session: Session, manager_id: Optional[int]) -> None:
    # session.get is tenant-scoped — a manager_id from another company comes
    # back None here, indistinguishable from "doesn't exist" (CLAUDE.md §5) —
    # never trust a cross-tenant FK blindly, even for a soft/non-sensitive field.
    if manager_id is not None and session.get(User, manager_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manager not found")


@router.post("/branches", response_model=BranchResponse, status_code=status.HTTP_201_CREATED)
def create_branch(
    body: BranchCreateRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> Branch:
    """CLAUDE.md §25: system_administrator only, within their own company —
    company_id is inherited from the admin, never chosen (§3/§4 pattern)."""
    _check_manager_id(session, body.manager_id)
    branch = Branch(
        name=body.name,
        code=body.code,
        address=body.address,
        manager_id=body.manager_id,
        delegated_limit=body.delegated_limit,
        company_id=admin.company_id,
    )
    session.add(branch)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Branch code already in use")

    write_audit(
        session,
        actor=admin,
        action=AuditAction.BRANCH_CREATE.value,
        entity_type="Branch",
        entity_id=branch.id,
        reason=f"code={body.code}",
        company_id=admin.company_id,
    )
    session.commit()
    session.refresh(branch)
    return branch


@router.patch("/branches/{branch_id}", response_model=BranchResponse)
def update_branch(
    branch_id: int,
    body: BranchUpdateRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> Branch:
    branch = get_or_404(session, Branch, branch_id, detail="Branch not found")

    updates = body.model_dump(exclude_unset=True)
    if "manager_id" in updates:
        _check_manager_id(session, updates["manager_id"])
    for field, value in updates.items():
        setattr(branch, field, value)

    session.add(branch)
    write_audit(
        session,
        actor=admin,
        action=AuditAction.BRANCH_UPDATE.value,
        entity_type="Branch",
        entity_id=branch_id,
        reason=", ".join(f"{k}={v}" for k, v in updates.items()),
        company_id=admin.company_id,
    )
    session.commit()
    session.refresh(branch)
    return branch


@router.get("/kyc", response_model=list[ComplianceProfileResponse])
def get_all_kyc_profiles(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> list[ComplianceProfileResponse]:
    """CLAUDE.md §9: company-wide KYC oversight — every profile regardless of
    status, unlike the compliance officer's pending-only queue."""
    rows = session.exec(
        select(Profile, User).join(User, User.id == Profile.user_id).order_by(Profile.created_at.desc())
    ).all()
    return [_profile_to_response(profile, customer) for profile, customer in rows]


@router.get("/applications", response_model=list[CreditApplicationResponse])
def get_all_applications(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> list[CreditApplicationResponse]:
    """CLAUDE.md §9: company-wide application oversight — every status,
    unlike the credit officer's pending-only queue."""
    sync_loan_delinquency(session)
    # One joined query (application + customer + product + loan status)
    # instead of 1 + 3N round trips per row.
    rows = session.exec(
        select(LoanApplication, User, LoanProduct, Loan.status)
        .join(User, User.id == LoanApplication.customer_id)
        .join(LoanProduct, LoanProduct.id == LoanApplication.loan_product_id)
        .outerjoin(Loan, Loan.application_id == LoanApplication.id)
        .order_by(LoanApplication.created_at.desc())
    ).all()
    return [_application_row_to_response(a, c, p, ls) for a, c, p, ls in rows]


@router.get("/loans", response_model=list[AdminLoanResponse])
def get_all_loans(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> list[AdminLoanResponse]:
    sync_loan_delinquency(session)
    rows = session.exec(
        select(Loan, User, LoanProduct)
        .join(User, User.id == Loan.customer_id)
        .join(LoanProduct, LoanProduct.id == Loan.loan_product_id)
        .order_by(Loan.created_at.desc())
    ).all()
    return [
        AdminLoanResponse(
            id=loan.id,
            customer_full_name=customer.full_name,
            customer_email=customer.email,
            loan_product_name=product.name,
            principal=loan.principal,
            total_repayable=loan.total_repayable,
            penalties_accrued=loan.penalties_accrued,
            outstanding_balance=loan.outstanding_balance,
            status=loan.status.value,
            disbursed_at=loan.disbursed_at,
            created_at=loan.created_at,
        )
        for loan, customer, product in rows
    ]


@router.get("/products", response_model=list[AdminLoanProductResponse])
def get_all_products(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> list[LoanProduct]:
    """Unlike the customer-facing /loan-products, this includes inactive
    products too — system_administrator is the one who (de)activates them."""
    return list(session.exec(select(LoanProduct).order_by(LoanProduct.id)).all())


@router.patch("/products/{product_id}", response_model=AdminLoanProductResponse)
def update_product(
    product_id: int,
    body: LoanProductUpdateRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> LoanProduct:
    product = get_or_404(session, LoanProduct, product_id, detail="Product not found")

    updates = body.model_dump(exclude_unset=True)
    if "min_amount" in updates or "max_amount" in updates:
        new_min = updates.get("min_amount", product.min_amount)
        new_max = updates.get("max_amount", product.max_amount)
        if new_min > new_max:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="min_amount cannot exceed max_amount")
    if "interest_model" in updates:
        updates["interest_model"] = InterestModel(updates["interest_model"])
    for field, value in updates.items():
        setattr(product, field, value)

    session.add(product)
    write_audit(
        session,
        actor=admin,
        action=AuditAction.LOAN_PRODUCT_UPDATE.value,
        entity_type="LoanProduct",
        entity_id=product_id,
        reason=", ".join(f"{k}={v}" for k, v in updates.items()),
        company_id=admin.company_id,
    )
    session.commit()
    session.refresh(product)
    return product


@router.get("/portfolio/summary", response_model=PortfolioSummaryResponse)
def get_portfolio_summary(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> PortfolioSummaryResponse:
    """CLAUDE.md §9: aggregates only, no individual customer PII — a
    read-only rollup a future executive role can be pointed at unchanged.
    Computation lives in app/portfolio.py (shared with the branch-scoped and
    management-level equivalents, CLAUDE.md §29/§30) — this endpoint's own
    URL/response shape is unchanged.
    """
    summary = compute_portfolio_summary(session)
    return PortfolioSummaryResponse(
        total_disbursed=summary.total_disbursed,
        total_collected=summary.total_collected,
        active_borrowers=summary.active_borrowers,
        active_loans=summary.active_loans,
        outstanding_principal=summary.outstanding_principal,
        par_percentage=summary.par_percentage,
        overdue_loans=summary.overdue_loans,
        defaulted_loans=summary.defaulted_loans,
        loans_disbursed_this_month=summary.loans_disbursed_this_month,
        as_of=summary.as_of,
    )


@router.get("/portfolio/trend", response_model=PortfolioTrendResponse)
def get_portfolio_trend(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> PortfolioTrendResponse:
    """CLAUDE.md §20: sparkline data for the dashboard's hero stat — daily
    disbursement activity over the trailing window, computed from existing
    Loan rows (no new table, no stored history to maintain)."""
    points = compute_portfolio_trend(session)
    return PortfolioTrendResponse(
        points=[
            PortfolioTrendPoint(date=p.date, disbursed_count=p.disbursed_count, disbursed_amount=p.disbursed_amount)
            for p in points
        ]
    )


def _admin_previously_overrode_kyc_for_customer(session: Session, admin_id: int, customer_user_id: int) -> bool:
    """CLAUDE.md §8 anomaly guard: has this admin already overridden a KYC
    decision belonging to this same applicant? Override volume is tiny in the
    MVP, so resolving each prior override's Profile.user_id one at a time is
    fine — no need for a join against a column AuditLog doesn't have."""
    prior_overrides = session.exec(
        select(AuditLog.entity_id).where(
            AuditLog.actor_id == admin_id,
            AuditLog.action == AuditAction.KYC_OVERRIDE.value,
            AuditLog.entity_type == "Profile",
        )
    ).all()
    for profile_id in prior_overrides:
        profile = session.get(Profile, profile_id)
        if profile is not None and profile.user_id == customer_user_id:
            return True
    return False


def _admin_previously_overrode_application_for_customer(
    session: Session, admin_id: int, customer_user_id: int
) -> bool:
    prior_overrides = session.exec(
        select(AuditLog.entity_id).where(
            AuditLog.actor_id == admin_id,
            AuditLog.action == AuditAction.APPLICATION_OVERRIDE.value,
            AuditLog.entity_type == "LoanApplication",
        )
    ).all()
    for application_id in prior_overrides:
        application = session.get(LoanApplication, application_id)
        if application is not None and application.customer_id == customer_user_id:
            return True
    return False


@router.post("/kyc/{profile_id}/override", response_model=ComplianceProfileResponse)
def override_kyc_decision(
    profile_id: int,
    body: KYCOverrideRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> ComplianceProfileResponse:
    """CLAUDE.md §8: exceptional, reasoned, and distinctly audited — never
    the normal path (that ends at the compliance officer's own decision).
    Only applies to an already-decided profile; a pending one goes through
    the normal compliance queue, not this."""
    profile = get_or_404(session, Profile, profile_id, detail="Profile not found")
    if profile.kyc_status == KYCStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot override a decision that hasn't been made yet")

    original_status = profile.kyc_status
    new_status = KYCStatus(body.new_status)
    if new_status == original_status:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Profile is already {new_status.value}")

    # CLAUDE.md §14: compare-and-set, never a blind UPDATE.
    result = session.execute(
        update(Profile)
        .where(Profile.id == profile_id, Profile.kyc_status == original_status)
        .values(
            kyc_status=new_status,
            reviewed_by=admin.id,
            reviewed_at=datetime.now(timezone.utc),
            review_notes=body.reason,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile was changed by someone else, please retry")

    is_anomaly = _admin_previously_overrode_application_for_customer(session, admin.id, profile.user_id)
    write_audit(
        session,
        actor=admin,
        action=AuditAction.KYC_OVERRIDE.value,
        entity_type="Profile",
        entity_id=profile_id,
        reason=f"{body.reason} (reversed from {original_status.value} to {new_status.value})",
        company_id=admin.company_id,
        is_anomaly=is_anomaly,
    )
    session.commit()

    session.refresh(profile)
    customer = session.get(User, profile.user_id)
    return _profile_to_response(profile, customer)


@router.post("/applications/{application_id}/override", response_model=LoanApprovalResponse)
def override_application_decision(
    application_id: int,
    body: ApplicationOverrideRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> LoanApprovalResponse:
    """CLAUDE.md §8: "reactivate a wrongly-rejected application" — the named
    example. Only rejected -> approved is supported (see
    ApplicationOverrideRequest's docstring for why the reverse isn't)."""
    application = get_or_404(session, LoanApplication, application_id, detail="Application not found")
    if application.status != ApplicationStatus.rejected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a rejected application can be reactivated by override",
        )

    customer = session.get(User, application.customer_id)
    product = session.get(LoanProduct, application.loan_product_id)
    if customer is None or product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    # CLAUDE.md §14: compare-and-set, never a blind UPDATE.
    result = session.execute(
        update(LoanApplication)
        .where(LoanApplication.id == application_id, LoanApplication.status == ApplicationStatus.rejected)
        .values(
            status=ApplicationStatus.approved,
            reviewed_by=admin.id,
            reviewed_at=datetime.now(timezone.utc),
            review_notes=body.reason,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application was changed by someone else, please retry")

    loan, due_date = create_loan_for_application(session, application, product)

    is_anomaly = _admin_previously_overrode_kyc_for_customer(session, admin.id, application.customer_id)
    write_audit(
        session,
        actor=admin,
        action=AuditAction.APPLICATION_OVERRIDE.value,
        entity_type="LoanApplication",
        entity_id=application_id,
        reason=f"{body.reason} (reversed from rejected to approved)",
        company_id=admin.company_id,
        is_anomaly=is_anomaly,
    )
    session.commit()

    application = session.get(LoanApplication, application_id)
    session.refresh(loan)
    return LoanApprovalResponse(
        application=_application_to_response(session, application, customer, product),
        loan=LoanResponse(
            id=loan.id,
            application_id=loan.application_id,
            principal=loan.principal,
            interest_rate=loan.interest_rate,
            total_repayable=loan.total_repayable,
            penalties_accrued=loan.penalties_accrued,
            outstanding_balance=loan.outstanding_balance,
            status=loan.status.value,
        ),
        repayment_due_date=due_date,
        repayment_amount_due=loan.total_repayable,
    )
