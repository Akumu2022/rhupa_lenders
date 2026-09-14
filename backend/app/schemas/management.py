from decimal import Decimal

from pydantic import BaseModel


class BranchRankingItemResponse(BaseModel):
    branch_id: int
    branch_name: str
    branch_code: str
    total_disbursed: Decimal
    outstanding_principal: Decimal
    par_percentage: Decimal
    active_loans: int


class StaffPerformanceItemResponse(BaseModel):
    staff_id: int
    full_name: str
    role: str
    branch_name: str | None
    decisions_made: int
    approvals: int
    rejections: int
