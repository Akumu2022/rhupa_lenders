"""Sidebar alert counts: how many items are waiting on the signed-in user, keyed
by the sidebar item's path (frontend/src/components/nav.ts).

Read-only and role-aware. Each count mirrors the queue that role's own page
shows, so the red badge and the page always agree. Tenant scoping comes from
the central filter (CLAUDE.md §5) — nothing here filters on company_id.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import get_session
from ..deps import get_current_user
from ..models import (
    ApplicationStatus,
    KYCStatus,
    Loan,
    LoanApplication,
    LoanStatus,
    Profile,
    User,
    UserRole,
)

router = APIRouter(tags=["nav-badges"])


def _count(session: Session, statement) -> int:
    return session.exec(statement).one()


@router.get("/nav-badges", response_model=dict[str, int])
def get_nav_badges(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    pending_kyc = select(func.count()).select_from(Profile).where(Profile.kyc_status == KYCStatus.pending)
    badges: dict[str, int] = {}

    if user.role == UserRole.credit_officer:
        badges["/compliance/queue"] = _count(session, pending_kyc)

    elif user.role == UserRole.system_administrator:
        badges["/admin/kyc"] = _count(session, pending_kyc)

    elif user.role == UserRole.branch_manager:
        badges["/branch-manager/applications"] = _count(
            session,
            select(func.count())
            .select_from(LoanApplication)
            .where(
                LoanApplication.status == ApplicationStatus.pending_branch_review,
                LoanApplication.branch_id == user.branch_id,
            ),
        )

    elif user.role == UserRole.loan_vetting_committee:
        badges["/committee/queue"] = _count(
            session,
            select(func.count())
            .select_from(LoanApplication)
            .where(LoanApplication.status == ApplicationStatus.pending_committee_review),
        )

    elif user.role == UserRole.cashier_finance_officer:
        badges["/finance/disbursements"] = _count(
            session, select(func.count()).select_from(Loan).where(Loan.status == LoanStatus.approved)
        )

    elif user.role == UserRole.customer:
        # A rejected KYC needs the customer to fix and resubmit (CLAUDE.md §10).
        badges["/customer/profile"] = _count(
            session,
            select(func.count())
            .select_from(Profile)
            .where(Profile.user_id == user.id, Profile.kyc_status == KYCStatus.rejected),
        )
        badges["/customer/repayments"] = _count(
            session,
            select(func.count())
            .select_from(Loan)
            .where(Loan.customer_id == user.id, Loan.status == LoanStatus.overdue),
        )

    return {path: count for path, count in badges.items() if count > 0}
