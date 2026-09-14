"""CLAUDE.md §9/§26 (M13): branch manager — decides applications escalated
from their own credit officers, within a delegated limit; above it, only
"escalate" to the committee is available. Branch-scoped visibility into
staff/portfolio/collections (§9) — an ordinary hand-filtered branch_id
query, never the tenant-isolation mechanism itself (§5's asymmetry).
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, update
from sqlmodel import Session, select

from ..application_review import check_no_self_approval, write_review_stage
from ..audit import write_audit
from ..db import get_session
from ..deps import require_role
from ..loan_delinquency import sync_loan_delinquency
from ..time_utils import as_utc
from ..models import (
    ApplicationStatus,
    AuditAction,
    Branch,
    Loan,
    LoanApplication,
    LoanProduct,
    LoanStatus,
    RepaymentSchedule,
    ReviewDecision,
    ReviewStage,
    User,
    UserRole,
)
from ..portfolio import compute_portfolio_summary
from ..schemas.admin import PortfolioSummaryResponse
from ..schemas.branch_manager import ApplicationDecisionRequest, BranchQueueItemResponse
from ..schemas.credit import CollectionsQueueItemResponse, CreditApplicationResponse
from ..schemas.user import UserResponse
from .credit import _to_response, create_loan_for_application

router = APIRouter(prefix="/branch-manager", tags=["branch-manager"])


def _effective_limit(branch_limit: Decimal | None, product_limit: Decimal) -> Decimal:
    """CLAUDE.md §26: min(branch override, product default) — never
    silently the larger/looser figure."""
    if branch_limit is not None:
        return min(branch_limit, product_limit)
    return product_limit


@router.get("/queue", response_model=list[BranchQueueItemResponse])
def get_branch_queue(
    session: Session = Depends(get_session),
    manager: User = Depends(require_role(UserRole.branch_manager)),
) -> list[BranchQueueItemResponse]:
    rows = session.exec(
        select(LoanApplication, User, LoanProduct)
        .join(User, User.id == LoanApplication.customer_id)
        .join(LoanProduct, LoanProduct.id == LoanApplication.loan_product_id)
        .where(
            LoanApplication.status == ApplicationStatus.pending_branch_review,
            LoanApplication.branch_id == manager.branch_id,
        )
        .order_by(LoanApplication.created_at)
    ).all()

    responses = []
    for application, customer, product in rows:
        limit = _effective_limit(None, product.branch_manager_delegated_limit)
        responses.append(
            BranchQueueItemResponse(
                id=application.id,
                customer_full_name=customer.full_name,
                customer_email=customer.email,
                loan_product_name=product.name,
                amount_requested=application.amount_requested,
                created_at=application.created_at,
                effective_limit=limit,
                over_limit=application.amount_requested > limit,
            )
        )
    return responses


def _get_branch_application_bundle(
    session: Session, application_id: int, branch_id: int | None
) -> tuple[LoanApplication, User, LoanProduct]:
    application = session.get(LoanApplication, application_id)
    if application is None or application.branch_id != branch_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    customer = session.get(User, application.customer_id)
    product = session.get(LoanProduct, application.loan_product_id)
    if customer is None or product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application, customer, product


@router.post("/applications/{application_id}/decide", response_model=CreditApplicationResponse)
def decide_branch_application(
    application_id: int,
    body: ApplicationDecisionRequest,
    session: Session = Depends(get_session),
    manager: User = Depends(require_role(UserRole.branch_manager)),
) -> CreditApplicationResponse:
    application, customer, product = _get_branch_application_bundle(session, application_id, manager.branch_id)
    # Status checked before the no-self-approval check so a plain double
    # decide (the same manager retrying/double-clicking) reads as "already
    # decided" (409) rather than the more alarming "you already acted on
    # this" (403) — both are correctly refused either way.
    if application.status != ApplicationStatus.pending_branch_review:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application is not awaiting branch review")
    # CLAUDE.md §8/§26: no-self-approval — same user can never occupy two
    # stages of one application's chain.
    check_no_self_approval(session, application_id, manager.id)

    branch = session.get(Branch, manager.branch_id)
    limit = _effective_limit(branch.delegated_limit if branch else None, product.branch_manager_delegated_limit)
    over_limit = application.amount_requested > limit

    if body.decision == "reject":
        result = session.execute(
            update(LoanApplication)
            .where(LoanApplication.id == application_id, LoanApplication.status == ApplicationStatus.pending_branch_review)
            .values(
                status=ApplicationStatus.rejected,
                reviewed_by=manager.id,
                reviewed_at=datetime.now(timezone.utc),
                review_notes=body.comments,
            )
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application is not awaiting branch review")
        write_review_stage(
            session,
            application_id=application_id,
            company_id=manager.company_id,
            stage=ReviewStage.branch_review,
            actor_id=manager.id,
            decision=ReviewDecision.reject,
            comments=body.comments,
        )
        write_audit(
            session, actor=manager, action=AuditAction.APPLICATION_REJECT.value,
            entity_type="LoanApplication", entity_id=application_id, reason=body.comments,
            company_id=manager.company_id,
        )
        session.commit()

    elif body.decision == "escalate":
        if not over_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount is within your delegated limit — approve or reject directly",
            )
        result = session.execute(
            update(LoanApplication)
            .where(LoanApplication.id == application_id, LoanApplication.status == ApplicationStatus.pending_branch_review)
            .values(status=ApplicationStatus.pending_committee_review)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application is not awaiting branch review")
        write_review_stage(
            session,
            application_id=application_id,
            company_id=manager.company_id,
            stage=ReviewStage.branch_review,
            actor_id=manager.id,
            decision=ReviewDecision.escalate,
            comments=body.comments,
        )
        write_audit(
            session, actor=manager, action=AuditAction.APPLICATION_ESCALATE.value,
            entity_type="LoanApplication", entity_id=application_id, reason=body.comments,
            company_id=manager.company_id,
        )
        session.commit()

    else:  # approve
        if over_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount exceeds your delegated limit — escalate to the committee instead",
            )
        result = session.execute(
            update(LoanApplication)
            .where(LoanApplication.id == application_id, LoanApplication.status == ApplicationStatus.pending_branch_review)
            .values(
                status=ApplicationStatus.approved,
                reviewed_by=manager.id,
                reviewed_at=datetime.now(timezone.utc),
                review_notes=body.comments,
            )
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application is not awaiting branch review")
        create_loan_for_application(session, application, product)
        write_review_stage(
            session,
            application_id=application_id,
            company_id=manager.company_id,
            stage=ReviewStage.branch_review,
            actor_id=manager.id,
            decision=ReviewDecision.approve,
            comments=body.comments,
        )
        # CLAUDE.md §19 light exception monitoring: an approval landed within
        # a minute of submission is fast enough to be worth a second look —
        # flagged onto the exceptions list via is_anomaly, not blocked.
        seconds_to_decision = (datetime.now(timezone.utc) - as_utc(application.created_at)).total_seconds()
        write_audit(
            session, actor=manager, action=AuditAction.APPLICATION_APPROVE.value,
            entity_type="LoanApplication", entity_id=application_id, reason=body.comments,
            company_id=manager.company_id, is_anomaly=seconds_to_decision < 60,
        )
        session.commit()

    application, customer, product = _get_branch_application_bundle(session, application_id, manager.branch_id)
    return _to_response(session, application, customer, product)


@router.get("/staff", response_model=list[UserResponse])
def get_branch_staff(
    session: Session = Depends(get_session),
    manager: User = Depends(require_role(UserRole.branch_manager)),
) -> list[User]:
    return list(
        session.exec(select(User).where(User.branch_id == manager.branch_id).order_by(User.full_name)).all()
    )


@router.get("/portfolio", response_model=PortfolioSummaryResponse)
def get_branch_portfolio(
    session: Session = Depends(get_session),
    manager: User = Depends(require_role(UserRole.branch_manager)),
) -> PortfolioSummaryResponse:
    summary = compute_portfolio_summary(session, branch_id=manager.branch_id)
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


@router.get("/collections", response_model=list[CollectionsQueueItemResponse])
def get_branch_collections(
    session: Session = Depends(get_session),
    manager: User = Depends(require_role(UserRole.branch_manager)),
) -> list[CollectionsQueueItemResponse]:
    """Same shape/logic as credit.py's collections queue, filtered to this
    manager's own branch via the borrower's User.branch_id."""
    sync_loan_delinquency(session)

    loan_rows = session.exec(
        select(Loan, User, LoanProduct)
        .join(User, User.id == Loan.customer_id)
        .join(LoanProduct, LoanProduct.id == Loan.loan_product_id)
        .where(Loan.status == LoanStatus.overdue, User.branch_id == manager.branch_id)
        .order_by(Loan.id)
    ).all()

    today = date.today()
    loan_ids = [loan.id for loan, _, _ in loan_rows]
    earliest_overdue_by_loan: dict[int, date] = {}
    if loan_ids:
        earliest_overdue_by_loan = dict(
            session.exec(
                select(RepaymentSchedule.loan_id, func.min(RepaymentSchedule.due_date))
                .where(
                    RepaymentSchedule.loan_id.in_(loan_ids),
                    RepaymentSchedule.is_paid.is_(False),
                    RepaymentSchedule.due_date < today,
                )
                .group_by(RepaymentSchedule.loan_id)
            ).all()
        )

    responses = []
    for loan, customer, product in loan_rows:
        earliest_overdue = earliest_overdue_by_loan.get(loan.id)
        if earliest_overdue is None:
            continue
        responses.append(
            CollectionsQueueItemResponse(
                id=loan.id,
                customer_full_name=customer.full_name,
                customer_email=customer.email,
                loan_product_name=product.name,
                outstanding_balance=loan.outstanding_balance,
                status=loan.status.value,
                earliest_overdue_due_date=earliest_overdue,
                days_overdue=(today - earliest_overdue).days,
            )
        )
    return responses
