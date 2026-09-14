from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..models import UserRole


class StaffCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    # CLAUDE.md §4/§8: a system_administrator creates their own company's
    # staff, never another system_administrator or super_admin through this
    # endpoint.
    role: Literal[
        "credit_officer",
        "branch_manager",
        "loan_vetting_committee",
        "cashier_finance_officer",
        "management",
    ]
    # CLAUDE.md §4/§25: required for credit_officer/branch_manager, optional
    # for the company-wide roles. Validated server-side against the creating
    # admin's own company_id — never trusted blindly (see app/routers/staff.py).
    branch_id: Optional[int] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    company_id: Optional[int]
    branch_id: Optional[int]
    is_active: bool
