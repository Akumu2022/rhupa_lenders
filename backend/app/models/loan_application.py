import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class ApplicationStatus(str, enum.Enum):
    # `pending` is kept for old rows (never issued by new submissions after
    # M13) — the multi-stage chain, CLAUDE.md §26:
    # submitted -> pending_branch_review -> [pending_committee_review] ->
    # approved | rejected. There is no separate pending_finance_review
    # *application* status — once approved, the resulting Loan's own ladder
    # (CLAUDE.md §28) is what finance acts on; approved/rejected stay the
    # only terminal states here.
    pending = "pending"
    pending_branch_review = "pending_branch_review"
    pending_committee_review = "pending_committee_review"
    approved = "approved"
    rejected = "rejected"


class LoanApplication(TenantMixin, table=True):
    """CLAUDE.md M4/§10/§26: Handoff 2 — submission writes
    status=pending_branch_review (or pending_committee_review when the
    applicant has no branch) and stamps branch_id; the branch manager's
    queue (M13) is just a filtered query over these two fields.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="user.id", index=True)
    loan_product_id: int = Field(foreign_key="loanproduct.id", index=True)
    amount_requested: Decimal = Field(max_digits=12, decimal_places=2)

    # CLAUDE.md §26: resolved server-side from the applicant's own
    # User.branch_id at submission — never from the request body. Null for
    # an applicant with no branch (a self-signup customer); such
    # applications go straight to committee review since there is no branch
    # manager to route them to.
    branch_id: Optional[int] = Field(default=None, foreign_key="branch.id", index=True)

    # CLAUDE.md §11: every reviewable entity carries status + reviewer fields.
    # reviewed_by/reviewed_at/review_notes are the LAST decision's summary
    # (kept for the existing single-glance views); the full per-stage trail
    # lives in ApplicationReviewStage (append-only, CLAUDE.md §26).
    status: ApplicationStatus = Field(default=ApplicationStatus.pending_branch_review, index=True)
    reviewed_by: Optional[int] = Field(default=None, foreign_key="user.id")
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

    # Indexed — every oversight/queue endpoint sorts on this (ORDER BY
    # created_at [DESC]); senior-review finding, previously unindexed.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
