"""Sidebar alert counts: how many items are waiting on the signed-in user, keyed
by the sidebar item's path (frontend/src/components/nav.ts).

Read-only and role-aware. Each count mirrors the queue that role's own page
shows, so the red badge and the page always agree. Tenant scoping comes from
the central filter (CLAUDE.md §5) — nothing here filters on company_id.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

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
    Transaction,
    TransactionType,
    User,
    UserRole,
)

router = APIRouter(tags=["nav-badges"])


def _count(session: Session, statement) -> int:
    return session.exec(statement).one()


@router.get("/nav-badges", response_model=dict[str, int])
def get_nav_badges(
    payments_since: Optional[datetime] = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    pending_kyc = select(func.count()).select_from(Profile).where(Profile.kyc_status == KYCStatus.pending)
    badges: dict[str, int] = {}

    # Repayments recorded since the viewer last opened the page that lists
    # them — every channel counts (customer portal, staff-recorded, and the
    # bank collections API), full or partial. "Last opened" is kept by the
    # browser and sent here; default is the last 24h, never older than a week.
    now = datetime.now(timezone.utc)
    since = payments_since or now - timedelta(days=1)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    since = max(since.astimezone(timezone.utc), now - timedelta(days=7)).replace(tzinfo=None)
    new_payments = (
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.type == TransactionType.repayment, Transaction.created_at > since)
    )

    if user.role == UserRole.credit_officer:
        badges["/compliance/queue"] = _count(session, pending_kyc)
        badges["/credit/collections"] = _count(
            session,
            new_payments.join(User, User.id == Transaction.customer_id).where(User.assigned_officer_id == user.id),
        )

    elif user.role == UserRole.system_administrator:
        badges["/admin/kyc"] = _count(session, pending_kyc)
        badges["/admin/collections"] = _count(session, new_payments)

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

        badges["/branch-manager/collections"] = _count(
            session,
            new_payments.join(User, User.id == Transaction.customer_id).where(User.branch_id == user.branch_id),
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
        badges["/finance/loans"] = _count(session, new_payments)

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
