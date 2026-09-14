"""CLAUDE.md §19: active -> overdue is a system-computed transition (no
Celery/APScheduler at this scale — see CLAUDE.md §2), recomputed on demand by
every read path that needs an accurate delinquency picture (the collections
queue, portfolio summary, company-wide loan oversight, a customer's own
loans). overdue -> defaulted is never done here — that's always an explicit,
reasoned staff action (app/routers/credit.py::mark_loan_defaulted).

Both status updates below are inherently safe without a per-row
expected-version check: each is filtered on the CURRENT status it
promotes/demotes FROM, so a loan that has moved on for any other reason (e.g.
a concurrent repayment completed it) simply falls out of the WHERE clause and
is left untouched.

CLAUDE.md §23: penalty accrual on overdue loans piggybacks on this same
on-demand recompute, for the identical reason — one central place, no
scheduler yet, rather than a second job with its own cadence.
"""

from datetime import date

from sqlalchemy import update
from sqlmodel import Session, select

from .loan_calculation import apply_daily_penalties
from .models import Loan, LoanProduct, LoanStatus, RepaymentSchedule


def sync_loan_delinquency(session: Session) -> None:
    today = date.today()
    overdue_loan_ids = list(
        session.exec(
            select(RepaymentSchedule.loan_id).where(
                RepaymentSchedule.is_paid.is_(False), RepaymentSchedule.due_date < today
            )
        ).all()
    )

    if overdue_loan_ids:
        session.execute(
            update(Loan)
            .where(Loan.status == LoanStatus.active, Loan.id.in_(overdue_loan_ids))
            .values(status=LoanStatus.overdue)
        )

    # Demote back to active any loan currently flagged overdue that no longer
    # has an overdue unpaid installment (e.g. it was just paid off).
    still_overdue_subquery = select(RepaymentSchedule.loan_id).where(
        RepaymentSchedule.is_paid.is_(False), RepaymentSchedule.due_date < today
    )
    session.execute(
        update(Loan)
        .where(Loan.status == LoanStatus.overdue, Loan.id.not_in(still_overdue_subquery))
        .values(status=LoanStatus.active)
    )

    if overdue_loan_ids:
        overdue_loans = session.exec(
            select(Loan).where(Loan.status == LoanStatus.overdue, Loan.id.in_(overdue_loan_ids))
        ).all()
        for loan in overdue_loans:
            product = session.get(LoanProduct, loan.loan_product_id)
            if product is not None:
                apply_daily_penalties(session, loan, product, today=today)

    session.commit()
