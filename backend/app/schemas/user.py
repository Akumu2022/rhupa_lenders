from datetime import datetime
from decimal import Decimal
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


class StaffPasswordResetRequest(BaseModel):
    """system_administrator resetting one of their own staff's forgotten
    password — no old-password confirmation (that's the whole point of an
    admin-assisted reset), staff only, same-company only (enforced in the
    router, same tenant-scoped lookup as deactivate/reactivate)."""

    new_password: str = Field(min_length=8)


class PlatformPasswordResetRequest(BaseModel):
    """super_admin resetting ANY user's password (any company, any role) —
    the one deliberate cross-tenant surface, same as every other
    /platform/... route. Reason is required, same convention as every other
    platform-tier action (CLAUDE.md §6)."""

    new_password: str = Field(min_length=8)
    reason: str = Field(min_length=1)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    company_id: Optional[int]
    branch_id: Optional[int]
    is_active: bool


class StaffHandledApplication(BaseModel):
    id: int
    customer_id: int
    customer_full_name: str
    loan_product_name: str
    amount_requested: Decimal
    status: str
    # How this staff member touched it: prepared / decided (latest decision)
    # / a review stage.
    involvement: str
    created_at: datetime


class StaffActivityItem(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: Optional[int]
    reason: Optional[str]
    created_at: datetime


class StaffDetailResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    branch_id: Optional[int]
    branch_name: Optional[str]
    is_active: bool
    assigned_customers: int
    applications: list[StaffHandledApplication]
    recent_activity: list[StaffActivityItem]
