from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class BusinessAssessment(TenantMixin, table=True):
    """CLAUDE.md §27 (M11): client PRD §2B. One row per Profile (1:1,
    upsert-style via app/routers/customers.py) — onboarding/appraisal data
    about the customer's business, not a per-LoanApplication snapshot (the
    PRD places this under the Credit Officer Module's registration section,
    before Loan Application). `net_income` and `debt_service_capacity` are
    ALWAYS server-computed by app/customer_registration.py's single source
    of truth — never accepted as client input, same discipline as
    app/loan_calculation.py's money math (§23).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True, unique=True)

    business_name: str
    business_type: str
    ownership: str
    physical_location: str
    years_in_operation: int

    sales_frequency: str  # "daily" | "weekly" | "monthly" — which period total_income covers
    total_income: Decimal = Field(max_digits=12, decimal_places=2)
    total_expenses: Decimal = Field(max_digits=12, decimal_places=2)
    reported_profit: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    stock_value: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    existing_loans_amount: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    other_lenders: Optional[str] = None
    bank_mpesa_turnover: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    business_assets_value: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    cash_flow_notes: Optional[str] = None
    existing_debt_obligations: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)

    # Computed — see app/customer_registration.py::compute_business_figures.
    # net_income = total_income - total_expenses
    # debt_service_capacity = net_income - existing_debt_obligations
    net_income: Decimal = Field(max_digits=12, decimal_places=2)
    debt_service_capacity: Decimal = Field(max_digits=12, decimal_places=2)

    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
