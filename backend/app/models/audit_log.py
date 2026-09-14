import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class AuditAction(str, enum.Enum):
    """Every audit `action` string used anywhere in the app, in one place —
    a typo here (e.g. a route passing a bare string that drifts from this
    list) is now a lookup error at import/lint time, not a silently
    unsearchable row in an append-only legal record. `AuditLog.action`
    itself stays a plain `str` column (not this enum) since the set of
    valid actions may grow without a migration — call sites pass
    `AuditAction.X.value` explicitly.
    """

    BRANCH_CREATE = "branch.create"
    BRANCH_UPDATE = "branch.update"
    STAFF_CREATE = "staff.create"
    STAFF_DEACTIVATE = "staff.deactivate"
    STAFF_REACTIVATE = "staff.reactivate"
    LOAN_PRODUCT_UPDATE = "loan_product.update"
    KYC_VERIFY = "kyc.verify"
    KYC_REJECT = "kyc.reject"
    KYC_OVERRIDE = "kyc.override"
    APPLICATION_APPROVE = "application.approve"
    APPLICATION_REJECT = "application.reject"
    APPLICATION_OVERRIDE = "application.override"
    APPLICATION_RAPID_SUBMISSION = "application.rapid_submission"
    LOAN_DISBURSE = "loan.disburse"
    LOAN_MARK_DEFAULTED = "loan.mark_defaulted"
    LOAN_REPAY = "loan.repay"
    LOAN_PENALTY_APPLIED = "loan.penalty_applied"
    CUSTOMER_REGISTER = "customer.register"
    REFEREE_ADD = "referee.add"
    BUSINESS_ASSESSMENT_CREATE = "business_assessment.create"
    BUSINESS_ASSESSMENT_UPDATE = "business_assessment.update"
    COMPANY_CREATE = "company.create"
    COMPANY_SUSPEND = "company.suspend"
    COMPANY_REACTIVATE = "company.reactivate"
    COMPANY_UPDATE_PROFILE = "company.update_profile"


class AuditLog(TenantMixin, table=True):
    """Append-only trail (CLAUDE.md §12). No route/service ever UPDATEs or DELETEs
    a row here — there is simply no code path that does it.

    `company_id` (inherited from TenantMixin) is the *target* company for a
    platform action (e.g. which company got suspended) or the acting company for
    a company-tier action — never both meanings at once for a given row.
    `is_platform_action` disambiguates the tier explicitly rather than relying on
    company_id being null/non-null, per CLAUDE.md §12.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    actor_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    actor_email: str  # denormalized — survives the actor account being deleted later

    action: str = Field(index=True)
    entity_type: str
    entity_id: Optional[int] = None

    reason: Optional[str] = None
    is_platform_action: bool = Field(default=False, index=True)

    # CLAUDE.md §8 anomaly guard: true when this override is the SAME
    # system_administrator overriding both a KYC decision and a loan decision on the
    # SAME applicant — the one-person-does-everything scenario separation of
    # duties exists to prevent. Must be visible distinctly in the exceptions
    # list, not just recoverable by cross-referencing the log by hand.
    is_anomaly: bool = Field(default=False, index=True)

    # Indexed — /admin/audit-log sorts on this (ORDER BY created_at DESC
    # LIMIT 500); senior-review finding, previously unindexed.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
