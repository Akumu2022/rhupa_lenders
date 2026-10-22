"""Due-date payment prompts (STK push) — run once a day, mid-morning.

For each company that switched STK push on, every instalment that is due today
or overdue gets a prompt to the borrower's phone for what is still unpaid on
that instalment. The prompt only asks; the money arrives later through the bank
collections API (app/routers/collections_api.py) and is recorded there, so this
module never touches a balance.

Guard rails, because this contacts real people:
  * only inside business hours (08:00-18:59 Africa/Nairobi) — outside them the
    run does nothing at all;
  * at most one prompt per instalment per day, at least 3 days apart, and at
    most 3 prompts per instalment in total;
  * only loans still being serviced (active / overdue), never defaulted or
    written-off ones, and never for a suspended company;
  * every prompt is its own audit entry (rule #11), which is also what the
    limits above are counted from — there is no second table to drift.

The gateway is simulated today (app/payment_gateway.py): nothing is sent.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from .audit import write_system_audit
from .disbursement import customer_phone
from .models import (
    AuditAction,
    AuditLog,
    Company,
    CompanyStatus,
    Loan,
    LoanStatus,
    Profile,
    RepaymentSchedule,
)
from .payment_gateway import get_gateway
from .tenancy import tenant_context
from .time_utils import as_utc, business_tz

MAX_PROMPTS_PER_INSTALMENT = 3
MIN_DAYS_BETWEEN_PROMPTS = 3
FIRST_HOUR, LAST_HOUR = 8, 18  # inclusive, business time


@dataclass
class StkRun:
    business_date: str
    sent: int = 0
    failed: int = 0
    skipped_outside_hours: bool = False
    failed_company_ids: list[int] = field(default_factory=list)


def run_stk_reminders(session: Session, *, now: Optional[datetime] = None) -> StkRun:
    local_now = (now or datetime.now(business_tz())).astimezone(business_tz())
    today = local_now.date()
    result = StkRun(business_date=today.isoformat())
    if not FIRST_HOUR <= local_now.hour <= LAST_HOUR:
        result.skipped_outside_hours = True
        return result

    with tenant_context(None):  # platform-level listing of tenants only
        company_ids = [
            c.id
            for c in session.exec(
                select(Company).where(Company.status == CompanyStatus.active, Company.stk_push_enabled == True)  # noqa: E712
            ).all()
        ]

    gateway = get_gateway()
    for company_id in company_ids:
        with tenant_context(company_id):
            try:
                sent, failed = _prompt_company(session, gateway, today)
                session.commit()
                result.sent += sent
                result.failed += failed
            except Exception:
                # One company's bad data must not stop the others.
                session.rollback()
                result.failed_company_ids.append(company_id)
    return result


def _prompt_company(session: Session, gateway, today) -> tuple[int, int]:
    due = session.exec(
        select(RepaymentSchedule, Loan)
        .join(Loan, Loan.id == RepaymentSchedule.loan_id)
        .where(
            RepaymentSchedule.is_paid == False,  # noqa: E712
            RepaymentSchedule.due_date <= today,
            Loan.status.in_([LoanStatus.active, LoanStatus.overdue]),
        )
        .order_by(RepaymentSchedule.id)
    ).all()
    if not due:
        return 0, 0

    history: dict[int, list[datetime]] = {}
    for entity_id, created_at in session.exec(
        select(AuditLog.entity_id, AuditLog.created_at).where(
            AuditLog.action == AuditAction.STK_PUSH_REQUESTED.value,
            AuditLog.entity_type == "RepaymentSchedule",
            AuditLog.entity_id.in_([schedule.id for schedule, _ in due]),
        )
    ).all():
        history.setdefault(entity_id, []).append(created_at)

    sent = failed = 0
    for schedule, loan in due:
        remaining = schedule.amount_due - schedule.amount_paid
        if remaining <= Decimal("0.00"):
            continue
        previous = history.get(schedule.id, [])
        if len(previous) >= MAX_PROMPTS_PER_INSTALMENT:
            continue
        if previous:
            last_day = max(as_utc(t) for t in previous).astimezone(business_tz()).date()
            if (today - last_day).days < MIN_DAYS_BETWEEN_PROMPTS:
                continue

        phone = customer_phone(session, loan.customer_id)
        customer_number = session.exec(select(Profile.customer_number).where(Profile.user_id == loan.customer_id)).first()
        outcome = gateway.request_payment(
            idempotency_key=f"STK-{schedule.id}-{today.isoformat()}",
            amount=remaining,
            phone=phone,
            account_ref=customer_number or "",
        )
        write_system_audit(
            session,
            action=AuditAction.STK_PUSH_REQUESTED.value,
            entity_type="RepaymentSchedule",
            entity_id=schedule.id,
            reason=(
                f"{today.isoformat()} prompt {len(previous) + 1}: KES {remaining} to ***{phone[-4:]} "
                f"for loan {loan.id} - {'ok' if outcome.ok else 'FAILED'}: {outcome.message}"
            ),
            company_id=loan.company_id,
        )
        if outcome.ok:
            sent += 1
        else:
            failed += 1
    return sent, failed
