"""CLAUDE.md §23: the money-critical module — the ONE backend source of
truth for loan interest, amortization, and penalty math. Routers call
`generate_schedule` / `apply_daily_penalties`; nothing else computes real
money, and the frontend never does either (it may preview, never bind).

Rounding: every monetary result is rounded ROUND_HALF_UP to the cent as soon
as it is produced. Decimal end to end, never float (CLAUDE.md §13).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import update
from sqlmodel import Session, select

from .audit import write_system_audit
from .models import AuditAction, InterestModel, Loan, LoanProduct, PenaltyType, RepaymentSchedule, Transaction, TransactionType

CENT = Decimal("0.01")
_ZERO = Decimal("0.00")


def round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class ScheduledInstallment:
    installment_number: int
    due_date: date
    principal_component: Decimal
    interest_component: Decimal

    @property
    def amount_due(self) -> Decimal:
        return self.principal_component + self.interest_component


@dataclass
class LoanSchedule:
    installments: list[ScheduledInstallment]

    @property
    def total_principal(self) -> Decimal:
        return sum((i.principal_component for i in self.installments), _ZERO)

    @property
    def total_interest(self) -> Decimal:
        return sum((i.interest_component for i in self.installments), _ZERO)

    @property
    def total_repayable(self) -> Decimal:
        return self.total_principal + self.total_interest


def _split_evenly(total: Decimal, count: int) -> list[Decimal]:
    """Splits `total` into `count` rounded shares that sum EXACTLY back to
    `total` — the last share absorbs the rounding remainder so components
    never drift from the whole they must add up to."""
    if count == 1:
        return [round_money(total)]
    shares = [round_money(total / count) for _ in range(count - 1)]
    shares.append(round_money(total - sum(shares, _ZERO)))
    return shares


def _installment_due_dates(start_date: date, term_days: int, installment_count: int) -> list[date]:
    return [
        start_date + timedelta(days=(term_days * i) // installment_count) for i in range(1, installment_count + 1)
    ]


def _flat_schedule(
    *, principal: Decimal, rate_percent: Decimal, term_days: int, installment_count: int, start_date: date
) -> LoanSchedule:
    """CLAUDE.md §23: "principal x rate, fixed" — the rate applies ONCE over
    the whole term, independent of term length or installment count."""
    total_interest = round_money(principal * rate_percent / Decimal("100"))
    principal_shares = _split_evenly(principal, installment_count)
    interest_shares = _split_evenly(total_interest, installment_count)
    due_dates = _installment_due_dates(start_date, term_days, installment_count)
    return LoanSchedule(
        [
            ScheduledInstallment(i + 1, due_dates[i], principal_shares[i], interest_shares[i])
            for i in range(installment_count)
        ]
    )


def _reducing_balance_schedule(
    *, principal: Decimal, rate_percent: Decimal, term_days: int, installment_count: int, start_date: date
) -> LoanSchedule:
    """CLAUDE.md §23: "interest on shrinking balance (amortized)" — equal
    principal installments; each installment's interest is `rate_percent` of
    whatever principal is still outstanding BEFORE that installment, so
    interest shrinks installment-over-installment as the balance is paid
    down. With a single installment this is arithmetically identical to
    `flat` — the reduction only shows up once there's a balance left to
    reduce, i.e. installment_count > 1.
    """
    principal_shares = _split_evenly(principal, installment_count)
    due_dates = _installment_due_dates(start_date, term_days, installment_count)
    installments = []
    remaining = principal
    for i in range(installment_count):
        interest = round_money(remaining * rate_percent / Decimal("100"))
        installments.append(ScheduledInstallment(i + 1, due_dates[i], principal_shares[i], interest))
        remaining -= principal_shares[i]
    return LoanSchedule(installments)


def _daily_accrual_schedule(
    *, principal: Decimal, rate_percent: Decimal, term_days: int, installment_count: int, start_date: date
) -> LoanSchedule:
    """CLAUDE.md §23: "per-day on outstanding" — each installment's interest
    is `rate_percent` PER DAY on the balance outstanding during that
    installment's period, times the number of days that period spans. With a
    single installment this is principal * rate% * term_days — genuinely
    different from `flat` even when there's only one installment, because it
    scales with how long the term actually is."""
    principal_shares = _split_evenly(principal, installment_count)
    due_dates = _installment_due_dates(start_date, term_days, installment_count)
    installments = []
    remaining = principal
    period_start = start_date
    for i in range(installment_count):
        days_in_period = (due_dates[i] - period_start).days
        interest = round_money(remaining * rate_percent / Decimal("100") * days_in_period)
        installments.append(ScheduledInstallment(i + 1, due_dates[i], principal_shares[i], interest))
        remaining -= principal_shares[i]
        period_start = due_dates[i]
    return LoanSchedule(installments)


_DISPATCH = {
    InterestModel.flat: _flat_schedule,
    InterestModel.reducing_balance: _reducing_balance_schedule,
    InterestModel.daily_accrual: _daily_accrual_schedule,
}


def generate_schedule(
    *,
    principal: Decimal,
    rate_percent: Decimal,
    interest_model: InterestModel,
    term_days: int,
    installment_count: int,
    start_date: date,
) -> LoanSchedule:
    """The ONE dispatcher every caller uses — never call a specific model's
    function directly (CLAUDE.md §23). A 4th model later means adding an impl
    and registering it in `_DISPATCH`; nothing else changes."""
    return _DISPATCH[interest_model](
        principal=principal,
        rate_percent=rate_percent,
        term_days=term_days,
        installment_count=installment_count,
        start_date=start_date,
    )


def _penalty_cap(loan: Loan, product: LoanProduct) -> Decimal:
    return round_money(loan.principal * product.penalty_cap_ratio)


def apply_daily_penalties(session: Session, loan: Loan, product: LoanProduct, *, today: Optional[date] = None) -> None:
    """CLAUDE.md §23: an overdue loan accrues a penalty for each day past the
    product's grace period, capped so interest + penalties never exceed
    `penalty_cap_ratio` of principal (the DEV placeholder's safety mechanism
    against the "1%/day is runaway/predatory, uncapped" warning). Each day's
    penalty is its OWN ledger (Transaction) + audit (AuditLog) row — the owed
    amount never grows silently.

    Recomputed on demand from the loan's single unpaid overdue installment,
    the same way delinquency status itself is (see loan_delinquency.py, the
    only call site) rather than a separate APScheduler job — CLAUDE.md §2:
    no scheduler at this scale yet, and this keeps penalty accrual in the one
    place delinquency is already recomputed. Idempotent: calling this twice
    on the same day applies nothing the second time.
    """
    if product.penalty_type != PenaltyType.percentage_per_day:
        return  # only one penalty type implemented for now

    today = today or date.today()

    earliest_overdue_due_date = session.exec(
        select(RepaymentSchedule.due_date)
        .where(
            RepaymentSchedule.loan_id == loan.id,
            RepaymentSchedule.is_paid.is_(False),
            RepaymentSchedule.due_date < today,
        )
        .order_by(RepaymentSchedule.due_date)
    ).first()
    if earliest_overdue_due_date is None:
        return

    first_penalty_date = earliest_overdue_due_date + timedelta(days=product.grace_period_days)
    start_date = first_penalty_date
    if loan.last_penalty_check_date is not None and loan.last_penalty_check_date >= start_date:
        start_date = loan.last_penalty_check_date + timedelta(days=1)
    if start_date > today:
        return  # still within grace, or already caught up today

    base_interest = loan.total_repayable - loan.principal
    cap = _penalty_cap(loan, product)

    running_outstanding = loan.outstanding_balance
    running_penalties = loan.penalties_accrued
    daily_amounts: list[tuple[date, Decimal]] = []

    day = start_date
    while day <= today:
        headroom = max(cap - (base_interest + running_penalties), _ZERO)
        if headroom <= _ZERO:
            break
        day_penalty = min(round_money(running_outstanding * product.penalty_rate / Decimal("100")), headroom)
        if day_penalty <= _ZERO:
            break
        daily_amounts.append((day, day_penalty))
        running_outstanding += day_penalty
        running_penalties += day_penalty
        day += timedelta(days=1)

    # CLAUDE.md §14: compare-and-set, never a blind UPDATE — pinned to the
    # exact values this function read, so a concurrent write (another
    # request's sync, or a repayment) makes this a no-op rather than
    # clobbering it; the next sync call simply retries from fresh state.
    result = session.execute(
        update(Loan)
        .where(
            Loan.id == loan.id,
            Loan.penalties_accrued == loan.penalties_accrued,
            Loan.outstanding_balance == loan.outstanding_balance,
        )
        .values(
            penalties_accrued=running_penalties,
            outstanding_balance=running_outstanding,
            last_penalty_check_date=today,
        )
    )
    if result.rowcount == 0 or not daily_amounts:
        return

    for applied_day, amount in daily_amounts:
        session.add(
            Transaction(
                loan_id=loan.id,
                customer_id=loan.customer_id,
                company_id=loan.company_id,
                type=TransactionType.penalty,
                amount=amount,
            )
        )
        write_system_audit(
            session,
            action=AuditAction.LOAN_PENALTY_APPLIED.value,
            entity_type="Loan",
            entity_id=loan.id,
            reason=(
                f"{product.penalty_rate}%/day penalty for {applied_day.isoformat()} "
                f"(grace period {product.grace_period_days}d)"
            ),
            company_id=loan.company_id,
        )
