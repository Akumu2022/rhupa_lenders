"""Daily end-of-day run: overdue status and penalty accrual for every
company's loans, including loans nobody has opened that day.

The same work also runs on demand whenever a staff or customer screen loads
(app/loan_delinquency.py), and it is safe to repeat: penalties are applied
at most once per loan per business day. This run exists so accrual never
depends on someone happening to look. It is triggered by a scheduled GitHub
Action calling POST /internal/end-of-day (app/routers/internal.py), because
Render's free plan sleeps when idle, so an in-process timer would silently
miss days.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlmodel import Session, select

from .audit import write_system_audit
from .loan_delinquency import sync_loan_delinquency
from .models import AuditAction, Company, CompanyStatus
from .tenancy import tenant_context
from .time_utils import business_today


@dataclass
class CompanyRun:
    company_id: int
    newly_overdue: int
    back_to_active: int
    penalty_total: Decimal


@dataclass
class EndOfDayResult:
    business_date: str
    companies: list[CompanyRun] = field(default_factory=list)
    failed_company_ids: list[int] = field(default_factory=list)


def run_end_of_day(session: Session) -> EndOfDayResult:
    """One company at a time, each inside its own tenant context, so the
    central isolation filter (CLAUDE.md §5) applies exactly as it does for a
    request from that company. Suspended companies are included: their
    borrowers' loans still fall due (repayment stays open, §6)."""
    result = EndOfDayResult(business_date=business_today().isoformat())

    with tenant_context(None):  # platform-level listing of tenants only
        company_ids = [
            c.id
            for c in session.exec(
                select(Company).where(Company.status.in_([CompanyStatus.active, CompanyStatus.suspended]))
            ).all()
        ]

    for company_id in company_ids:
        with tenant_context(company_id):
            try:
                sync = sync_loan_delinquency(session)
                write_system_audit(
                    session,
                    action=AuditAction.END_OF_DAY_RUN.value,
                    entity_type="Company",
                    entity_id=company_id,
                    reason=(
                        f"{result.business_date}: {sync.newly_overdue} newly overdue, "
                        f"{sync.back_to_active} back to active, penalties {sync.penalty_total}"
                    ),
                    company_id=company_id,
                )
                session.commit()
                result.companies.append(
                    CompanyRun(company_id, sync.newly_overdue, sync.back_to_active, sync.penalty_total)
                )
            except Exception:
                # One company's bad data must not stop the others' run.
                session.rollback()
                result.failed_company_ids.append(company_id)
    return result
