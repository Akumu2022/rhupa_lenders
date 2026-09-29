import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class GuarantorVerificationStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class Guarantor(TenantMixin, table=True):
    """CLAUDE.md §27 (M12): a guarantor pledged against one specific loan
    application — captured by the credit officer while preparing it, viewed
    by branch_manager/committee at decision time. `consent` is a stored
    attestation (the officer confirming the guarantor agreed), not a raw
    signature image, per §27's own wording.

    Adaptation of the client spec's "cannot be submitted without guarantors"
    rule to this codebase's actual flow: applications are submitted directly
    by the customer (POST /applications), before a credit officer has a
    chance to attach guarantors — so the gate that matters here is at
    *decision* time (branch_manager/committee "approve"), not at submission.
    See app/application_review.py::require_guarantor_if_needed.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="loanapplication.id", index=True)

    full_name: str
    id_number: str
    phone_number: str
    occupation: Optional[str] = None
    residence: Optional[str] = None
    relationship: Optional[str] = None
    guaranteed_amount: Decimal = Field(max_digits=12, decimal_places=2)
    consent: bool = Field(default=False)

    verification_status: GuarantorVerificationStatus = Field(default=GuarantorVerificationStatus.pending)
    verified_by: Optional[int] = Field(default=None, foreign_key="user.id")
    verified_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
