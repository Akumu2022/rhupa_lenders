from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from .branch_manager import ApplicationDecisionRequest

# Committee has no delegated limit of its own to check — it IS the ceiling
# (CLAUDE.md §26) — so "escalate" isn't a valid decision here, but reusing
# the request shape keeps one convention across both stage-decision
# endpoints; the router itself only accepts approve/reject.
CommitteeDecisionRequest = ApplicationDecisionRequest


class CommitteeQueueItemResponse(BaseModel):
    id: int
    customer_full_name: str
    customer_email: str
    loan_product_name: str
    amount_requested: Decimal
    created_at: datetime
    # CLAUDE.md §26: "everything the branch manager saw plus the branch
    # manager's own decision/comments" — the committee never acts on an
    # application no branch manager has already reviewed.
    branch_manager_name: str
    branch_manager_comments: str = Field(min_length=1)
