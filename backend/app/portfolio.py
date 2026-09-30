"""Portfolio summaries and date-range reports, as thin views over
app/loan_analytics.py, the single source of every loan figure in the app.
Branch ranking and the finance/management reports call these; nothing here
computes money on its own, so no screen can drift from another.

Branch scope follows loan_analytics: a loan belongs to the branch its
application was made in (not the borrower's current branch).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from .loan_analytics import Scope, compute_dashboard
from .models import ExpenseEntry
from .time_utils import business_day_end_utc, business_day_start_utc, business_today


@dataclass
class PortfolioSummary:
    total_disbursed: Decimal
    total_collected: Decimal
    active_borrowers: int
    active_loans: int  # active + overdue + defaulted: everything still owed
    outstanding_principal: Decimal
    par_percentage: Decimal
    overdue_loans: int
    defaulted_loans: int
    loans_disbursed_this_month: int
    as_of: date


def compute_portfolio_summary(session: Session, *, branch_id: Optional[int] = None) -> PortfolioSummary:
    today = business_today()
    d = compute_dashboard(
        session, Scope(branch_id=branch_id), start=today.replace(day=1), end=today, include_names=False, today=today
    )
    p = d["portfolio"]
    return PortfolioSummary(
        total_disbursed=p["total_disbursed_all_time"],
        total_collected=p["total_repaid_all_time"],
        active_borrowers=p["active_borrowers"],
        active_loans=p["active_loans"] + p["overdue_loans"] + p["defaulted_loans"],
        outstanding_principal=p["outstanding_principal"],
        par_percentage=p["par_pct"],
        overdue_loans=p["overdue_loans"],
        defaulted_loans=p["defaulted_loans"],
        loans_disbursed_this_month=d["flows"]["disbursed_count"],
        as_of=today,
    )


@dataclass
class ReportSummary:
    start_date: date
    end_date: date
    total_disbursed: Decimal
    total_collected: Decimal
    total_expenses: Decimal
    net: Decimal
    par_percentage: Decimal
    active_loans: int


def compute_report(
    session: Session, *, start_date: date, end_date: date, branch_id: Optional[int] = None
) -> ReportSummary:
    """CLAUDE.md §30 M18: one parameterized date-range report for both
    finance and management. Money in/out comes from the analytics flows for
    the range; expenses come from the expense ledger; PAR and active loans
    are as of today."""
    d = compute_dashboard(session, Scope(branch_id=branch_id), start=start_date, end=end_date, include_names=False)

    expense_query = select(ExpenseEntry.amount).where(
        ExpenseEntry.created_at >= business_day_start_utc(start_date),
        ExpenseEntry.created_at <= business_day_end_utc(end_date),
    )
    if branch_id is not None:
        expense_query = expense_query.where(ExpenseEntry.branch_id == branch_id)
    total_expenses = sum(session.exec(expense_query).all(), Decimal("0.00"))

    collected = d["flows"]["collected_amount"]
    p = d["portfolio"]
    return ReportSummary(
        start_date=start_date,
        end_date=end_date,
        total_disbursed=d["flows"]["disbursed_amount"],
        total_collected=collected,
        total_expenses=total_expenses,
        net=collected - total_expenses,
        par_percentage=p["par_pct"],
        active_loans=p["active_loans"] + p["overdue_loans"] + p["defaulted_loans"],
    )
