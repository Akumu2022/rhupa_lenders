"""CLAUDE.md §9/§30 (M18): management — organization-wide, read-only
aggregates only, no individual customer PII on these screens. Built on the
same shared computation as /admin/portfolio/* (app/portfolio.py) so this
role can be pointed at the identical, already-correct figures.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func
from sqlmodel import Session, select

from ..db import get_session
from ..deps import require_role
from ..models import ApplicationReviewStage, Branch, ReviewDecision, User, UserRole
from ..portfolio import compute_portfolio_summary, compute_portfolio_trend, compute_report
from ..schemas.admin import PortfolioSummaryResponse, PortfolioTrendPoint, PortfolioTrendResponse
from ..schemas.management import BranchRankingItemResponse, StaffPerformanceItemResponse
from ..schemas.reports import ReportResponse

router = APIRouter(prefix="/management", tags=["management"])


@router.get("/portfolio", response_model=PortfolioSummaryResponse)
def get_management_portfolio(
    session: Session = Depends(get_session),
    exec: User = Depends(require_role(UserRole.management)),
) -> PortfolioSummaryResponse:
    summary = compute_portfolio_summary(session)
    return PortfolioSummaryResponse(
        total_disbursed=summary.total_disbursed,
        total_collected=summary.total_collected,
        active_borrowers=summary.active_borrowers,
        active_loans=summary.active_loans,
        outstanding_principal=summary.outstanding_principal,
        par_percentage=summary.par_percentage,
        overdue_loans=summary.overdue_loans,
        defaulted_loans=summary.defaulted_loans,
        loans_disbursed_this_month=summary.loans_disbursed_this_month,
        as_of=summary.as_of,
    )


@router.get("/portfolio/trend", response_model=PortfolioTrendResponse)
def get_management_portfolio_trend(
    session: Session = Depends(get_session),
    exec: User = Depends(require_role(UserRole.management)),
) -> PortfolioTrendResponse:
    points = compute_portfolio_trend(session)
    return PortfolioTrendResponse(
        points=[
            PortfolioTrendPoint(date=p.date, disbursed_count=p.disbursed_count, disbursed_amount=p.disbursed_amount)
            for p in points
        ]
    )


@router.get("/branch-ranking", response_model=list[BranchRankingItemResponse])
def get_branch_ranking(
    session: Session = Depends(get_session),
    exec: User = Depends(require_role(UserRole.management)),
) -> list[BranchRankingItemResponse]:
    branches = session.exec(select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.name)).all()
    items = []
    for branch in branches:
        summary = compute_portfolio_summary(session, branch_id=branch.id)
        items.append(
            BranchRankingItemResponse(
                branch_id=branch.id,
                branch_name=branch.name,
                branch_code=branch.code,
                total_disbursed=summary.total_disbursed,
                outstanding_principal=summary.outstanding_principal,
                par_percentage=summary.par_percentage,
                active_loans=summary.active_loans,
            )
        )
    return sorted(items, key=lambda i: i.total_disbursed, reverse=True)


@router.get("/staff-performance", response_model=list[StaffPerformanceItemResponse])
def get_staff_performance(
    session: Session = Depends(get_session),
    exec: User = Depends(require_role(UserRole.management)),
) -> list[StaffPerformanceItemResponse]:
    """CLAUDE.md §26 made ApplicationReviewStage the source of truth for
    every decision going forward (branch manager + committee) — credit
    officers prepare but no longer decide, so they carry no rows here."""
    rows = session.exec(
        select(
            ApplicationReviewStage.actor_id,
            func.count(ApplicationReviewStage.id),
            func.count(case((ApplicationReviewStage.decision == ReviewDecision.approve, 1), else_=None)),
            func.count(case((ApplicationReviewStage.decision == ReviewDecision.reject, 1), else_=None)),
        ).group_by(ApplicationReviewStage.actor_id)
    ).all()

    items = []
    for actor_id, total, approvals, rejections in rows:
        staff = session.get(User, actor_id)
        if staff is None:
            continue
        branch = session.get(Branch, staff.branch_id) if staff.branch_id else None
        items.append(
            StaffPerformanceItemResponse(
                staff_id=staff.id,
                full_name=staff.full_name,
                role=staff.role.value,
                branch_name=branch.name if branch else None,
                decisions_made=total,
                approvals=approvals,
                rejections=rejections,
            )
        )
    return sorted(items, key=lambda i: i.decisions_made, reverse=True)


@router.get("/reports", response_model=ReportResponse)
def get_management_report(
    start_date: date,
    end_date: date,
    session: Session = Depends(get_session),
    exec: User = Depends(require_role(UserRole.management)),
) -> ReportResponse:
    if start_date > end_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_date must not be after end_date")
    report = compute_report(session, start_date=start_date, end_date=end_date)
    return ReportResponse(
        start_date=report.start_date,
        end_date=report.end_date,
        total_disbursed=report.total_disbursed,
        total_collected=report.total_collected,
        total_expenses=report.total_expenses,
        net=report.net,
        par_percentage=report.par_percentage,
        active_loans=report.active_loans,
    )
