import enum
from decimal import Decimal
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class InterestModel(str, enum.Enum):
    """CLAUDE.md §23: strategy-pattern selector — app/loan_calculation.py's
    dispatcher picks the impl by this field. Never branch on it anywhere else.
    """

    flat = "flat"
    reducing_balance = "reducing_balance"
    daily_accrual = "daily_accrual"


class PenaltyType(str, enum.Enum):
    """CLAUDE.md §23: only one type is implemented for the MVP — a percentage
    of the amount owed, applied per day overdue (the DEV placeholder is
    1%/day). The enum exists so a second type (e.g. a flat fee) can be added
    later without changing LoanProduct's shape.
    """

    percentage_per_day = "percentage_per_day"


class LoanProduct(TenantMixin, table=True):
    """CLAUDE.md M4: seeded per company (Salary Advance, Emergency, Business).
    system_administrator can create/edit further products beyond the seeded
    defaults (app/routers/admin.py) — never a hard delete, since existing
    loans/applications reference a product; `is_active` is the retire lever.

    CLAUDE.md §23: interest_model + installment_count select which of the
    three schedule shapes app/loan_calculation.py generates; the penalty_*
    fields are DEV PLACEHOLDER FIGURES (NOT FINAL — Finance must revise before
    production) but already live as per-product config, not hard-coded, so
    that revision is a config change, never a code change.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    min_amount: Decimal = Field(max_digits=12, decimal_places=2)
    max_amount: Decimal = Field(max_digits=12, decimal_places=2)
    interest_rate: Decimal = Field(max_digits=5, decimal_places=2)  # percent; meaning depends on interest_model
    repayment_period_days: int
    is_active: bool = Field(default=True)

    interest_model: InterestModel = Field(default=InterestModel.flat)
    # Installments per loan. MVP products are all single bullet-repayment
    # (1) — the engine supports more so reducing_balance/daily_accrual can be
    # exercised meaningfully once a product configures more than one.
    installment_count: int = Field(default=1)

    penalty_type: PenaltyType = Field(default=PenaltyType.percentage_per_day)
    # DEV PLACEHOLDER: 1% per day on the overdue amount. NOT FINAL.
    penalty_rate: Decimal = Field(default=Decimal("1.00"), max_digits=5, decimal_places=2)
    # DEV PLACEHOLDER: 3 days before penalties start (due_date + 3). NOT FINAL.
    grace_period_days: int = Field(default=3)
    # DEV PLACEHOLDER: interest + penalties capped at 100% of principal — MUST
    # confirm the current CBK DCP cap before production. Expressed as a ratio
    # of principal (1.00 = 100%).
    penalty_cap_ratio: Decimal = Field(default=Decimal("1.00"), max_digits=5, decimal_places=2)

    # CLAUDE.md §26 (M13): a branch manager may decide an application on this
    # product directly, without committee review, only up to this amount.
    # DEV PLACEHOLDER — Finance/ops must revise before production, same
    # caveat as the penalty config above; lives as config, not code.
    branch_manager_delegated_limit: Decimal = Field(
        default=Decimal("100000.00"), max_digits=12, decimal_places=2
    )

    # CLAUDE.md §27 (M12): when true, an application on this product cannot
    # be *approved* (branch manager or committee) without at least one
    # verified Guarantor attached — see app/application_review.py. Default
    # False so existing seeded products are unaffected.
    requires_guarantor: bool = Field(default=False)
