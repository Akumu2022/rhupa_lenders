"""CLAUDE.md §29/§30: shared aggregate/report logic — extracted out of
app/routers/admin.py (whose /admin/portfolio/* endpoints keep their exact
URL and response shape, just delegating here now) so
app/routers/branch_manager.py and app/routers/management.py can reuse the
same computation for their branch-scoped and company-wide views instead of
copy-pasting it.

Also where the CLAUDE.md §29-flagged PAR bug is fixed: PAR must be
outstanding PRINCIPAL of loans in arrears over gross outstanding PRINCIPAL,
not the interest+penalty-inclusive outstanding_balance.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, case, func
from sqlmodel import Session, select

from .loan_delinquency import sync_loan_delinquency
from .time_utils import business_date, business_day_end_utc, business_day_start_utc, business_today
from .models import ExpenseEntry, Loan, LoanStatus, RepaymentSchedule, Transaction, TransactionType, User

_TREND_DAYS = 14

_OUTSTANDING_STATUSES = (LoanStatus.active, LoanStatus.overdue, LoanStatus.defaulted)
_AT_RISK_STATUSES = (LoanStatus.overdue, LoanStatus.defaulted)


class PortfolioSummary:
    """Plain data holder — routers build their own Pydantic response model
    from this (their response shapes already differ slightly, e.g. the
    branch-scoped one doesn't need `as_of` repeated)."""

    def __init__(
        self,
        *,
        total_disbursed: Decimal,
        total_collected: Decimal,
        active_borrowers: int,
        active_loans: int,
        outstanding_principal: Decimal,
        par_percentage: Decimal,
        overdue_loans: int,
        defaulted_loans: int,
        loans_disbursed_this_month: int,
        as_of: date,
    ) -> None:
        self.total_disbursed = total_disbursed
        self.total_collected = total_collected
        self.active_borrowers = active_borrowers
        self.active_loans = active_loans
        self.outstanding_principal = outstanding_principal
        self.par_percentage = par_percentage
        self.overdue_loans = overdue_loans
        self.defaulted_loans = defaulted_loans
        self.loans_disbursed_this_month = loans_disbursed_this_month
        self.as_of = as_of


def _principal_repaid(loan_row) -> Decimal:
    """Principal actually repaid: the loan's stored running total, kept by
    app/repayments.py (payments clear penalties, then interest, then
    principal)."""
    return loan_row.principal_repaid


def compute_portfolio_summary(session: Session, *, branch_id: Optional[int] = None) -> PortfolioSummary:
    """Pure counts are computed in SQL; money sums are summed in Python over
    a narrow column-only projection — never SQL SUM() on a Numeric column
    (CLAUDE.md rule #13, see the long-form comment this replaced in
    admin.py for why). branch_id filters through User (Loan itself carries
    no branch_id, CLAUDE.md §25 — branch_id lives on the borrower's own
    User row)."""
    sync_loan_delinquency(session)

    outstanding_statuses = _OUTSTANDING_STATUSES
    today = business_today()
    month_start_dt = business_day_start_utc(today.replace(day=1))

    count_query = select(
        func.count(case((Loan.status.in_(outstanding_statuses), 1), else_=None)),
        func.count(case((Loan.status == LoanStatus.overdue, 1), else_=None)),
        func.count(case((Loan.status == LoanStatus.defaulted, 1), else_=None)),
        func.count(case((and_(Loan.disbursed_at.is_not(None), Loan.disbursed_at >= month_start_dt), 1), else_=None)),
    )
    row_query = select(
        Loan.status, Loan.principal, Loan.outstanding_balance, Loan.total_repayable, Loan.penalties_accrued,
        Loan.customer_id, Loan.principal_repaid, Loan.interest_repaid, Loan.penalties_repaid,
    )
    if branch_id is not None:
        count_query = count_query.join(User, User.id == Loan.customer_id).where(User.branch_id == branch_id)
        row_query = row_query.join(User, User.id == Loan.customer_id).where(User.branch_id == branch_id)

    active_loans, overdue_loan_count, defaulted_loan_count, loans_disbursed_this_month = session.exec(
        count_query
    ).one()
    rows = session.exec(row_query).all()

    total_disbursed = sum((r.principal for r in rows if r.status != LoanStatus.approved), Decimal("0.00"))
    outstanding_rows = [r for r in rows if r.status in outstanding_statuses]
    # Everything actually received, penalties included (the old
    # total_repayable - outstanding_balance undercounted it once penalties
    # had accrued).
    total_collected = sum(
        (
            r.principal_repaid + r.interest_repaid + r.penalties_repaid
            for r in rows
            if r.status in (*outstanding_statuses, LoanStatus.repaid)
        ),
        Decimal("0.00"),
    )
    active_borrowers = len({r.customer_id for r in outstanding_rows})

    # CLAUDE.md §29: PAR = outstanding PRINCIPAL of loans in arrears / gross
    # outstanding PRINCIPAL, not the interest+penalty-inclusive
    # outstanding_balance the previous implementation used.
    gross_outstanding_principal = sum(
        (r.principal - _principal_repaid(r) for r in outstanding_rows), Decimal("0.00")
    )
    at_risk_principal = sum(
        (r.principal - _principal_repaid(r) for r in outstanding_rows if r.status in _AT_RISK_STATUSES),
        Decimal("0.00"),
    )
    par_percentage = (
        (at_risk_principal / gross_outstanding_principal * Decimal("100")).quantize(Decimal("0.01"))
        if gross_outstanding_principal > 0
        else Decimal("0.00")
    )

    return PortfolioSummary(
        total_disbursed=total_disbursed,
        total_collected=total_collected,
        active_borrowers=active_borrowers,
        active_loans=active_loans,
        outstanding_principal=gross_outstanding_principal,
        par_percentage=par_percentage,
        overdue_loans=overdue_loan_count,
        defaulted_loans=defaulted_loan_count,
        loans_disbursed_this_month=loans_disbursed_this_month,
        as_of=today,
    )


class TrendPoint:
    def __init__(self, day: date, disbursed_count: int, disbursed_amount: Decimal) -> None:
        self.date = day
        self.disbursed_count = disbursed_count
        self.disbursed_amount = disbursed_amount


def compute_portfolio_trend(session: Session, *, branch_id: Optional[int] = None) -> list[TrendPoint]:
    """CLAUDE.md §20: sparkline data — daily disbursement activity over the
    trailing window, computed from existing Loan rows."""
    today = business_today()
    window_start = today - timedelta(days=_TREND_DAYS - 1)
    window_start_dt = business_day_start_utc(window_start)

    query = select(Loan).where(Loan.disbursed_at.is_not(None), Loan.disbursed_at >= window_start_dt)
    if branch_id is not None:
        query = query.join(User, User.id == Loan.customer_id).where(User.branch_id == branch_id)
    loans = session.exec(query).all()

    by_day: dict[date, list] = {window_start + timedelta(days=i): [] for i in range(_TREND_DAYS)}
    for loan in loans:
        day = business_date(loan.disbursed_at)
        if day in by_day:
            by_day[day].append(loan)

    return [
        TrendPoint(day, len(day_loans), sum((l.principal for l in day_loans), Decimal("0.00")))
        for day, day_loans in sorted(by_day.items())
    ]


class ReportSummary:
    def __init__(
        self,
        *,
        start_date: date,
        end_date: date,
        total_disbursed: Decimal,
        total_collected: Decimal,
        total_expenses: Decimal,
        net: Decimal,
        par_percentage: Decimal,
        active_loans: int,
    ) -> None:
        self.start_date = start_date
        self.end_date = end_date
        self.total_disbursed = total_disbursed
        self.total_collected = total_collected
        self.total_expenses = total_expenses
        self.net = net
        self.par_percentage = par_percentage
        self.active_loans = active_loans


def compute_report(
    session: Session, *, start_date: date, end_date: date, branch_id: Optional[int] = None
) -> ReportSummary:
    """CLAUDE.md §30 M18: a parameterized date-range report — one dispatcher
    (this function, called by both app/routers/finance.py and
    app/routers/management.py) rather than one hand-written endpoint per
    role/cadence, same "one dispatcher selected by a parameter" philosophy
    §23 already uses for interest models.
    """
    start_dt = business_day_start_utc(start_date)
    end_dt = business_day_end_utc(end_date)

    txn_query = select(Transaction.type, Transaction.amount, Transaction.customer_id).where(
        Transaction.created_at >= start_dt, Transaction.created_at <= end_dt
    )
    if branch_id is not None:
        txn_query = txn_query.join(User, User.id == Transaction.customer_id).where(User.branch_id == branch_id)
    txn_rows = session.exec(txn_query).all()

    total_disbursed = sum(
        (r.amount for r in txn_rows if r.type == TransactionType.disbursement), Decimal("0.00")
    )
    total_collected = sum((r.amount for r in txn_rows if r.type == TransactionType.repayment), Decimal("0.00"))

    expense_query = select(ExpenseEntry.amount).where(
        ExpenseEntry.created_at >= start_dt, ExpenseEntry.created_at <= end_dt
    )
    if branch_id is not None:
        expense_query = expense_query.where(ExpenseEntry.branch_id == branch_id)
    total_expenses = sum(session.exec(expense_query).all(), Decimal("0.00"))

    summary = compute_portfolio_summary(session, branch_id=branch_id)

    return ReportSummary(
        start_date=start_date,
        end_date=end_date,
        total_disbursed=total_disbursed,
        total_collected=total_collected,
        total_expenses=total_expenses,
        net=total_collected - total_expenses,
        par_percentage=summary.par_percentage,
        active_loans=summary.active_loans,
    )
