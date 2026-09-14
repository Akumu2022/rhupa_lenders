"""CLAUDE.md §9/§26 (M13): loan vetting committee — decides applications
escalated above a branch's delegated limit. Company-wide (not branch-
filtered): the committee reviews on behalf of the whole company, not one
branch. Never acts on an application no branch manager has already
reviewed — enforced simply by only ever querying
status=pending_committee_review, which an application only reaches via a
branch manager's escalation (or, for a branch-less applicant, directly at
submission — see app/routers/loans.py).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlmodel import Session, select

from ..application_review import check_no_self_approval, write_review_stage
from ..audit import write_audit
from ..db import get_session
from ..deps import require_role
from ..models import (
    ApplicationReviewStage,
    ApplicationStatus,
    AuditAction,
    LoanApplication,
    LoanProduct,
    ReviewDecision,
    ReviewStage,
    User,
    UserRole,
)
from ..schemas.committee import CommitteeDecisionRequest, CommitteeQueueItemResponse
from ..schemas.credit import CreditApplicationResponse
from .credit import _credit_application_base_query, _row_to_response, _to_response, create_loan_for_application

router = APIRouter(prefix="/committee", tags=["committee"])


def _get_application_bundle(session: Session, application_id: int) -> tuple[LoanApplication, User, LoanProduct]:
    application = session.get(LoanApplication, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    customer = session.get(User, application.customer_id)
    product = session.get(LoanProduct, application.loan_product_id)
    if customer is None or product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application, customer, product


@router.get("/queue", response_model=list[CommitteeQueueItemResponse])
def get_committee_queue(
    session: Session = Depends(get_session),
    member: User = Depends(require_role(UserRole.loan_vetting_committee)),
) -> list[CommitteeQueueItemResponse]:
    rows = session.exec(
        select(LoanApplication, User, LoanProduct)
        .join(User, User.id == LoanApplication.customer_id)
        .join(LoanProduct, LoanProduct.id == LoanApplication.loan_product_id)
        .where(LoanApplication.status == ApplicationStatus.pending_committee_review)
        .order_by(LoanApplication.created_at)
    ).all()

    responses = []
    for application, customer, product in rows:
        escalation = session.exec(
            select(ApplicationReviewStage, User)
            .join(User, User.id == ApplicationReviewStage.actor_id)
            .where(
                ApplicationReviewStage.application_id == application.id,
                ApplicationReviewStage.stage == ReviewStage.branch_review,
            )
            .order_by(ApplicationReviewStage.decided_at.desc())
        ).first()
        # A branch-less applicant's application reaches committee directly,
        # with no branch-review stage at all — shown plainly rather than
        # invented.
        branch_manager_name = escalation[1].full_name if escalation else "N/A (no branch)"
        branch_manager_comments = escalation[0].comments if escalation else "Applicant has no assigned branch."
        responses.append(
            CommitteeQueueItemResponse(
                id=application.id,
                customer_full_name=customer.full_name,
                customer_email=customer.email,
                loan_product_name=product.name,
                amount_requested=application.amount_requested,
                created_at=application.created_at,
                branch_manager_name=branch_manager_name,
                branch_manager_comments=branch_manager_comments,
            )
        )
    return responses


@router.post("/applications/{application_id}/decide", response_model=CreditApplicationResponse)
def decide_committee_application(
    application_id: int,
    body: CommitteeDecisionRequest,
    session: Session = Depends(get_session),
    member: User = Depends(require_role(UserRole.loan_vetting_committee)),
) -> CreditApplicationResponse:
    if body.decision == "escalate":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The committee is the final decision point")

    application, customer, product = _get_application_bundle(session, application_id)
    if application.status != ApplicationStatus.pending_committee_review:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application is not awaiting committee review")
    # CLAUDE.md §8/§26: no-self-approval — same user can never occupy two
    # stages of one application's chain (e.g. also having decided this one
    # as its branch manager, if roles were ever held by the same person).
    check_no_self_approval(session, application_id, member.id)

    new_status = ApplicationStatus.approved if body.decision == "approve" else ApplicationStatus.rejected
    result = session.execute(
        update(LoanApplication)
        .where(LoanApplication.id == application_id, LoanApplication.status == ApplicationStatus.pending_committee_review)
        .values(
            status=new_status,
            reviewed_by=member.id,
            reviewed_at=datetime.now(timezone.utc),
            review_notes=body.comments,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application is not awaiting committee review")

    if body.decision == "approve":
        create_loan_for_application(session, application, product)

    write_review_stage(
        session,
        application_id=application_id,
        company_id=member.company_id,
        stage=ReviewStage.committee_review,
        actor_id=member.id,
        decision=ReviewDecision.approve if body.decision == "approve" else ReviewDecision.reject,
        comments=body.comments,
    )
    write_audit(
        session,
        actor=member,
        action=(AuditAction.APPLICATION_APPROVE if body.decision == "approve" else AuditAction.APPLICATION_REJECT).value,
        entity_type="LoanApplication",
        entity_id=application_id,
        reason=body.comments,
        company_id=member.company_id,
    )
    session.commit()

    application, customer, product = _get_application_bundle(session, application_id)
    return _to_response(session, application, customer, product)


@router.get("/decisions/me", response_model=list[CreditApplicationResponse])
def get_my_committee_decisions(
    session: Session = Depends(get_session),
    member: User = Depends(require_role(UserRole.loan_vetting_committee)),
) -> list[CreditApplicationResponse]:
    rows = session.exec(
        _credit_application_base_query()
        .where(
            LoanApplication.reviewed_by == member.id,
            LoanApplication.status.in_((ApplicationStatus.approved, ApplicationStatus.rejected)),
        )
        .order_by(LoanApplication.reviewed_at.desc())
    ).all()
    return [_row_to_response(a, c, p, ls) for a, c, p, ls in rows]
