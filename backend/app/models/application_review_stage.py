import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class ReviewStage(str, enum.Enum):
    branch_review = "branch_review"
    committee_review = "committee_review"


class ReviewDecision(str, enum.Enum):
    approve = "approve"
    reject = "reject"
    escalate = "escalate"


class ApplicationReviewStage(TenantMixin, table=True):
    """CLAUDE.md §26: the append-only per-stage decision trail behind the
    multi-stage approval chain — never edited, a later correction goes
    through the system_administrator override path (§8) instead, same as
    every other decision in this app.

    Also the source of truth for the no-self-approval check (§8/§26): before
    writing any stage's decision, the caller checks the acting user's id
    does not already appear as `actor_id` on an earlier stage of the same
    application.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="loanapplication.id", index=True)
    stage: ReviewStage
    actor_id: int = Field(foreign_key="user.id", index=True)
    decision: ReviewDecision
    comments: str  # required — mirrors the existing credit-officer "required notes" convention
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
