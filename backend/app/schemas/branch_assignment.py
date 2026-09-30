from typing import Optional

from pydantic import BaseModel


class UnassignedUser(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    is_active: bool


class BranchAssignmentOverview(BaseModel):
    # Staff whose role requires a branch (credit officer, branch manager)
    # but who have none: their queues and dashboards can't work properly.
    staff_missing_branch: list[UnassignedUser]
    customers_missing_branch: list[UnassignedUser]
    # Applications with no branch: they skip branch review and go straight
    # to the committee.
    applications_without_branch: int


class AssignBranchRequest(BaseModel):
    # None clears the branch, allowed only for roles that don't require one.
    branch_id: Optional[int]


class AssignBranchResponse(BaseModel):
    user_id: int
    branch_id: Optional[int]
    rerouted_application_ids: list[int]


class SignupLinkResponse(BaseModel):
    # CLAUDE.md §7: the company's own administrator may view its signup code
    # to share it. Branch links add ?branch=<branch code>.
    signup_code: str

