"""Shared helpers for the multi-stage loan-application approval chain
(CLAUDE.md §26) — used by both app/routers/branch_manager.py and
app/routers/committee.py so the no-self-approval check and stage-writing
logic exists in exactly one place, not copy-pasted per role.
"""

from fastapi import HTTPException, status
from sqlmodel import Session, select

from .models import ApplicationReviewStage, ReviewDecision, ReviewStage


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
