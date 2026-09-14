from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ApplicationDecisionRequest(BaseModel):
    # CLAUDE.md §26: "escalate" is the only action available once an
    # application is over the branch's delegated limit — enforced
    # server-side (an over-limit "approve" is rejected, never trusted from
    # the client).
    decision: Literal["approve", "reject", "escalate"]
    comments: str = Field(min_length=1)


class BranchQueueItemResponse(BaseModel):
    id: int
    customer_full_name: str
    customer_email: str
    loan_product_name: str
    amount_requested: Decimal
    created_at: datetime
    # CLAUDE.md §26: min(branch override, product default) — shown so the
    # UI can disable "Approve"/"Reject" and only offer "Escalate" when true,
    # while the server enforces the same rule independently.
    effective_limit: Decimal
    over_limit: bool
