"""Shared helpers for the multi-stage loan-application approval chain
(CLAUDE.md §26) — used by both app/routers/branch_manager.py and
app/routers/committee.py so the no-self-approval check and stage-writing
logic exists in exactly one place, not copy-pasted per role.
"""

from fastapi import HTTPException, status
from sqlmodel import Session, select

from .models import ApplicationReviewStage, Guarantor, GuarantorVerificationStatus, LoanProduct, ReviewDecision, ReviewStage


def check_no_self_approval(session: Session, application_id: int, actor_id: int) -> None:
    """CLAUDE.md §8/§26: the same user may never occupy two stages of one
    application's decision chain — checked before writing any new stage."""
    prior = session.exec(
        select(ApplicationReviewStage.id).where(
            ApplicationReviewStage.application_id == application_id,
            ApplicationReviewStage.actor_id == actor_id,
        )
    ).first()
    if prior is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You have already acted on an earlier stage of this application",
        )


def write_review_stage(
    session: Session,
    *,
    application_id: int,
    company_id: int | None,
    stage: ReviewStage,
    actor_id: int,
    decision: ReviewDecision,
    comments: str,
) -> ApplicationReviewStage:
    entry = ApplicationReviewStage(
        application_id=application_id,
        company_id=company_id,
        stage=stage,
        actor_id=actor_id,
        decision=decision,
        comments=comments,
    )
    session.add(entry)
    return entry


def require_guarantor_if_needed(session: Session, application_id: int, product: LoanProduct) -> None:
    """CLAUDE.md §27 (M12): a product may require at least one verified
    guarantor before an application on it can be approved. Applications can
    be submitted either by the customer themselves or by a credit officer on
    their behalf (app/routers/loans.py) — either way, submission happens
    before a credit officer has necessarily had a chance to attach
    guarantors, so unlike the spec's literal "blocked at submission" wording,
    this codebase's equivalent gate is here, at approval time (the only point
    in the chain that actually creates a loan), called from both
    branch_manager.py and committee.py.
    """
    if not product.requires_guarantor:
        return
    verified = session.exec(
        select(Guarantor.id).where(
            Guarantor.application_id == application_id,
            Guarantor.verification_status == GuarantorVerificationStatus.verified,
        )
    ).first()
    if verified is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This product requires at least one verified guarantor before approval",
        )
