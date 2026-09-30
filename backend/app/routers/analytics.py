"""Shared staff analytics: one dashboard computation, one all-stages
applications list, one movement timeline — scoped by role server-side
(app/loan_analytics.py::scope_for), never by a client-supplied branch or
company. Read-only: no state changes, so no audit writes.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from ..db import get_session
from ..deps import require_role
from ..loan_analytics import (
    build_timeline,
    compute_dashboard,
    in_scope,
    list_applications,
    scope_for,
)
from ..models import LoanApplication, User, UserRole
from ..schemas.analytics import ApplicationListItem, DashboardResponse, TimelineResponse

router = APIRouter(prefix="/analytics", tags=["analytics"])

_DASHBOARD_ROLES = (
    UserRole.credit_officer,
    UserRole.branch_manager,
    UserRole.cashier_finance_officer,
    UserRole.management,
    UserRole.system_administrator,
)
# CLAUDE.md §9: management is aggregates-only — no named lists or per-loan
# drill-downs.
_DETAIL_ROLES = (
    UserRole.credit_officer,
    UserRole.branch_manager,
    UserRole.cashier_finance_officer,
    UserRole.system_administrator,
)


def _scope(user: User, mine: bool):
    return scope_for(user, mine=mine)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    mine: bool = Query(default=False),
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_DASHBOARD_ROLES)),
) -> dict:
    today = date.today()
    # Default range: month to date.
    start = start or today.replace(day=1)
    end = end or today
    if start > end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start must be on or before end")
    if (end - start).days > 3 * 366:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Date range may not exceed 3 years")
    return compute_dashboard(
        session,
        _scope(user, mine),
        start=start,
        end=end,
        include_names=user.role != UserRole.management,
        today=today,
    )


@router.get("/applications", response_model=list[ApplicationListItem])
def get_applications(
    mine: bool = Query(default=False),
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_DETAIL_ROLES)),
) -> list[dict]:
    return list_applications(session, _scope(user, mine))


@router.get("/applications/{application_id}/timeline", response_model=TimelineResponse)
def get_timeline(
    application_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_DETAIL_ROLES)),
) -> dict:
    # session.get is tenant-scoped (§5); the branch check narrows further
    # for branch-scoped roles. Both misses look identical (404).
    application = session.get(LoanApplication, application_id)
    if application is None or not in_scope(application, _scope(user, False)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return build_timeline(session, application)
