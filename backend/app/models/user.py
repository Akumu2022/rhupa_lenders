import enum
from typing import Optional

from sqlmodel import Field

from ..tenancy import TenantMixin


class UserRole(str, enum.Enum):
    """CLAUDE.md §3: replaced M10 to match the client PRD's own role names.
    `company_admin` -> `system_administrator`; `compliance_officer` retired
    (its KYC duties folded into `credit_officer`)."""

    super_admin = "super_admin"
    system_administrator = "system_administrator"
    credit_officer = "credit_officer"
    branch_manager = "branch_manager"
    loan_vetting_committee = "loan_vetting_committee"
    cashier_finance_officer = "cashier_finance_officer"
    management = "management"
    customer = "customer"


class User(TenantMixin, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    # Column width auto-sizes to the longest member on a fresh install, but an
    # existing Postgres column needs its migration to widen it explicitly —
    # same caveat as LoanStatus in models/loan.py.
    role: UserRole = Field(index=True)
    full_name: str

    # CLAUDE.md §25: required for credit_officer/branch_manager (their queues
    # and dashboards filter on it), optional for company-wide roles, null for
    # super_admin. An ordinary filterable column, NOT a tenant-isolation
    # boundary — company_id (via TenantMixin) is the only hard wall (§5).
    branch_id: Optional[int] = Field(default=None, foreign_key="branch.id", index=True)

    # CLAUDE.md §6: checked in the same central gate as company-suspension status,
    # on every request — a deactivated staff account loses access immediately.
    is_active: bool = Field(default=True)
