"""Branch assignment for a company's own people (system_administrator).

Accounts created before branches existed (M10), and customers who signed up
online without a branch link, have no branch. Branch-scoped staff then see
the wrong queues, and those customers' applications skip branch review and
go straight to the committee. This is where the administrator finds and
fixes them. branch_id is an ordinary column, not an isolation boundary
(CLAUDE.md §5); company isolation is still the central tenant filter.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, update
from sqlmodel import Session, select

from ..audit import write_audit
from ..db import get_session
from ..deps import require_role
from ..models import (
    ApplicationReviewStage,
    ApplicationStatus,
    AuditAction,
    Branch,
    Company,
    LoanApplication,
    User,
    UserRole,
)
from ..schemas.branch_assignment import (
    AssignBranchRequest,
    AssignBranchResponse,
    BranchAssignmentOverview,
    SignupLinkResponse,
    UnassignedUser,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# CLAUDE.md §25: these roles work within one branch and must have one.
BRANCH_REQUIRED_ROLES = (UserRole.credit_officer, UserRole.branch_manager)
_ASSIGNABLE_ROLES = (
    UserRole.credit_officer,
    UserRole.branch_manager,
    UserRole.loan_vetting_committee,
    UserRole.cashier_finance_officer,
    UserRole.management,
    UserRole.customer,
)


def _as_unassigned(user: User) -> UnassignedUser:
    return UnassignedUser(
        id=user.id, full_name=user.full_name, email=user.email, role=user.role.value, is_active=user.is_active
    )


@router.get("/branch-assignment", response_model=BranchAssignmentOverview)
def get_branch_assignment_overview(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> BranchAssignmentOverview:
    staff = session.exec(
        select(User).where(User.role.in_(BRANCH_REQUIRED_ROLES), User.branch_id.is_(None)).order_by(User.full_name)
    ).all()
    customers = session.exec(
        select(User).where(User.role == UserRole.customer, User.branch_id.is_(None)).order_by(User.full_name)
    ).all()
    without_branch = session.exec(
        select(func.count()).select_from(LoanApplication).where(LoanApplication.branch_id.is_(None))
    ).one()
    return BranchAssignmentOverview(
        staff_missing_branch=[_as_unassigned(u) for u in staff],
        customers_missing_branch=[_as_unassigned(u) for u in customers],
        applications_without_branch=without_branch,
    )


@router.patch("/users/{user_id}/branch", response_model=AssignBranchResponse)
def assign_branch(
    user_id: int,
    body: AssignBranchRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> AssignBranchResponse:
    # session.get is tenant-scoped: another company's user or branch comes
    # back None, indistinguishable from "doesn't exist" (CLAUDE.md §5).
    user = session.get(User, user_id)
    if user is None or user.role not in _ASSIGNABLE_ROLES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_branch = None
    if body.branch_id is not None:
        new_branch = session.get(Branch, body.branch_id)
        if new_branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
        if not new_branch.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch is inactive")
    elif user.role in BRANCH_REQUIRED_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This role requires a branch")

    old_branch_id = user.branch_id
    if old_branch_id == body.branch_id:
        return AssignBranchResponse(user_id=user.id, branch_id=old_branch_id, rerouted_application_ids=[])

    # CLAUDE.md §14: compare-and-set on the value we read.
    unchanged = User.branch_id.is_(None) if old_branch_id is None else User.branch_id == old_branch_id
    new_values: dict = {"branch_id": body.branch_id}
    if user.role == UserRole.customer and user.assigned_officer_id is not None:
        # A customer is only ever owned by an officer in their own branch.
        officer = session.get(User, user.assigned_officer_id)
        if officer is None or officer.branch_id != body.branch_id:
            new_values["assigned_officer_id"] = None
    result = session.execute(update(User).where(User.id == user.id, unchanged).values(**new_values))
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Branch was changed by someone else, reload and retry")

    write_audit(
        session,
        actor=admin,
        action=AuditAction.USER_BRANCH_CHANGE.value,
        entity_type="User",
        entity_id=user.id,
        reason=f"branch {old_branch_id or 'none'} -> {body.branch_id or 'none'}",
        company_id=admin.company_id,
    )

    rerouted: list[int] = []
    if user.role == UserRole.customer and new_branch is not None:
        rerouted = _reroute_unreviewed_applications(session, customer=user, branch=new_branch, admin=admin)

    session.commit()
    return AssignBranchResponse(user_id=user.id, branch_id=body.branch_id, rerouted_application_ids=rerouted)


def _reroute_unreviewed_applications(session: Session, *, customer: User, branch: Branch, admin: User) -> list[int]:
    """An application submitted while the customer had no branch went
    straight to the committee (there was no branch manager to send it to).
    If nobody has decided anything on it yet, send it through branch review
    as the chain intends (CLAUDE.md §26). Anything already reviewed is left
    exactly where it is."""
    candidates = session.exec(
        select(LoanApplication).where(
            LoanApplication.customer_id == customer.id,
            LoanApplication.branch_id.is_(None),
            LoanApplication.status == ApplicationStatus.pending_committee_review,
        )
    ).all()
    rerouted = []
    for application in candidates:
        already_reviewed = session.exec(
            select(ApplicationReviewStage.id).where(ApplicationReviewStage.application_id == application.id)
        ).first()
        if already_reviewed is not None:
            continue
        result = session.execute(
            update(LoanApplication)
            .where(
                LoanApplication.id == application.id,
                LoanApplication.status == ApplicationStatus.pending_committee_review,
                LoanApplication.branch_id.is_(None),
            )
            .values(branch_id=branch.id, status=ApplicationStatus.pending_branch_review)
        )
        if result.rowcount == 1:
            rerouted.append(application.id)
            write_audit(
                session,
                actor=admin,
                action=AuditAction.APPLICATION_REROUTE.value,
                entity_type="LoanApplication",
                entity_id=application.id,
                reason=f"customer assigned to branch {branch.code}: committee -> branch review",
                company_id=admin.company_id,
            )
    return rerouted


@router.get("/signup-link", response_model=SignupLinkResponse)
def get_signup_link(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> SignupLinkResponse:
    company = session.get(Company, admin.company_id)
    return SignupLinkResponse(signup_code=company.signup_code)
