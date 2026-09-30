"""The single place a repayment is applied to a loan — used by the
customer's own "repay now" and by staff recording money they received
(cash, M-Pesa, bank). One code path so the balance compare-and-set, the
schedule allocation, the ledger row, the receipt number and the audit entry
can never drift between the two.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .audit import write_audit
from .time_utils import business_today
from .models import (
    AuditAction,
    Company,
    Loan,
    LoanStatus,
    PaymentMethod,
    RepaymentSchedule,
    Transaction,
    TransactionType,
    User,
)

# CLAUDE.md §6: repayment stays open by default even once a loan has slipped
# into delinquency — don't trap a borrower who's trying to catch up.
REPAYABLE_LOAN_STATUSES = {LoanStatus.active, LoanStatus.overdue, LoanStatus.defaulted}

_ZERO = Decimal("0.00")


def normalize_reference(reference: Optional[str]) -> Optional[str]:
    """M-Pesa codes and bank refs are compared case- and space-insensitively,
    so "qab12 cd" and "QAB12CD" are recognised as the same payment."""
    if reference is None:
        return None
    cleaned = "".join(reference.split()).upper()
    return cleaned or None


def next_receipt_number(session: Session, company_id: int) -> str:
    """Sequential per company, via compare-and-set (rule #14) so two
    concurrent payments never share a receipt number."""
    company = session.get(Company, company_id)
    while True:
        current = company.next_receipt_sequence
        result = session.execute(
            update(Company)
            .where(Company.id == company.id, Company.next_receipt_sequence == current)
            .values(next_receipt_sequence=current + 1)
        )
        if result.rowcount == 1:
            company.next_receipt_sequence = current + 1
            return f"RCT-{company.id:04d}-{current:06d}"
        session.refresh(company)


@dataclass
class PaymentSplit:
    penalty: Decimal
    interest: Decimal
    principal: Decimal
    # (installment, amount applied to it). Penalties never touch the
    # schedule, which only carries principal + base interest.
    installments: list[tuple[RepaymentSchedule, Decimal]] = field(default_factory=list)


def _unpaid_schedule(session: Session, loan_id: int) -> list[RepaymentSchedule]:
    return list(
        session.exec(
            select(RepaymentSchedule)
            .where(RepaymentSchedule.loan_id == loan_id, RepaymentSchedule.is_paid.is_(False))
            .order_by(RepaymentSchedule.installment_number)
        ).all()
    )


def allocate_payment(loan: Loan, amount: Decimal, unpaid_schedule: list[RepaymentSchedule]) -> PaymentSplit:
    """Penalties first, then interest, then principal: the standard order
    for Kenyan lenders (confirmed by Finance). Within the schedule,
    instalments are settled oldest first, and inside each instalment its
    interest part is cleared before its principal part. Pure function (no
    writes), so it is unit-testable on its own."""
    remaining = amount
    penalties_due = max(loan.penalties_accrued - loan.penalties_repaid, _ZERO)
    to_penalty = min(remaining, penalties_due)
    remaining -= to_penalty

    to_interest = _ZERO
    to_principal = _ZERO
    applied: list[tuple[RepaymentSchedule, Decimal]] = []
    for installment in unpaid_schedule:
        if remaining <= _ZERO:
            break
        interest_paid_so_far = min(installment.amount_paid, installment.interest_component)
        interest_left = max(installment.interest_component - interest_paid_so_far, _ZERO)
        principal_left = max(installment.amount_due - installment.amount_paid - interest_left, _ZERO)

        pay_interest = min(remaining, interest_left)
        remaining -= pay_interest
        pay_principal = min(remaining, principal_left)
        remaining -= pay_principal

        if pay_interest + pay_principal > _ZERO:
            to_interest += pay_interest
            to_principal += pay_principal
            applied.append((installment, pay_interest + pay_principal))

    # The caller already checked amount <= outstanding_balance, and
    # outstanding == unpaid schedule + unpaid penalties, so nothing should be
    # left over. If a schedule rounding cent ever leaves a remainder, it
    # reduces principal rather than vanishing from the split.
    to_principal += remaining
    # Loans created before instalments carried an interest/principal split
    # have interest_component = 0, which would read every shilling as
    # principal. Principal can never be repaid beyond the principal itself;
    # any excess is interest.
    principal_room = max(loan.principal - loan.principal_repaid, _ZERO)
    if to_principal > principal_room:
        excess = to_principal - principal_room
        to_principal -= excess
        to_interest += excess
    return PaymentSplit(penalty=to_penalty, interest=to_interest, principal=to_principal, installments=applied)


def record_repayment(
    session: Session,
    *,
    loan: Loan,
    amount: Decimal,
    actor: User,
    method: PaymentMethod,
    reference: Optional[str] = None,
    notes: Optional[str] = None,
) -> Transaction:
    """Applies `amount` to `loan` and commits. Raises 400/409 HTTP errors for
    a closed loan, an overpayment, a concurrent balance change, or a payment
    reference that has already been recorded."""
    if loan.status not in REPAYABLE_LOAN_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Loan is not open for repayment")
    if amount > loan.outstanding_balance:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount exceeds outstanding balance")

    reference = normalize_reference(reference)
    if reference is not None:
        existing = session.exec(select(Transaction).where(Transaction.reference == reference)).first()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Payment reference {reference} was already recorded (receipt {existing.receipt_number or existing.id})",
            )

    split = allocate_payment(loan, amount, _unpaid_schedule(session, loan.id))
    new_balance = loan.outstanding_balance - amount
    # A partial payment doesn't change delinquency status here — the next
    # sync_loan_delinquency() recomputes overdue/active from the schedule,
    # the single source of truth for that (CLAUDE.md §19). A partially-paid
    # defaulted loan stays defaulted until fully repaid or an override.
    new_status = LoanStatus.repaid if new_balance <= _ZERO else loan.status

    # CLAUDE.md §14: compare-and-set on both status AND the balance being
    # decremented — a second concurrent repayment for the same loan sees a
    # rowcount of 0 and gets a 409 instead of silently double-spending it.
    result = session.execute(
        update(Loan)
        .where(
            Loan.id == loan.id,
            Loan.status == loan.status,
            Loan.outstanding_balance == loan.outstanding_balance,
        )
        .values(
            status=new_status,
            outstanding_balance=new_balance,
            penalties_repaid=loan.penalties_repaid + split.penalty,
            interest_repaid=loan.interest_repaid + split.interest,
            principal_repaid=loan.principal_repaid + split.principal,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Loan balance changed, please retry")

    for installment, applied in split.installments:
        installment.amount_paid += applied
        if installment.amount_paid >= installment.amount_due:
            installment.is_paid = True
        session.add(installment)

    # A payment that clears every past-due instalment brings an overdue loan
    # back to active straight away, instead of waiting for the next
    # delinquency sync. (Defaulted stays defaulted: that is a staff decision.)
    if new_status == LoanStatus.overdue:
        still_past_due = session.exec(
            select(RepaymentSchedule.id).where(
                RepaymentSchedule.loan_id == loan.id,
                RepaymentSchedule.is_paid.is_(False),
                RepaymentSchedule.due_date < business_today(),
            )
        ).first()
        if still_past_due is None:
            session.execute(
                update(Loan)
                .where(Loan.id == loan.id, Loan.status == LoanStatus.overdue)
                .values(status=LoanStatus.active)
            )

    is_staff = actor.id != loan.customer_id
    transaction = Transaction(
        loan_id=loan.id,
        customer_id=loan.customer_id,
        company_id=loan.company_id,
        type=TransactionType.repayment,
        amount=amount,
        method=method,
        reference=reference,
        receipt_number=next_receipt_number(session, loan.company_id),
        recorded_by=actor.id if is_staff else None,
        notes=notes,
        penalty_portion=split.penalty,
        interest_portion=split.interest,
        principal_portion=split.principal,
    )
    session.add(transaction)
    write_audit(
        session,
        actor=actor,
        action=(AuditAction.LOAN_PAYMENT_RECORDED if is_staff else AuditAction.LOAN_REPAY).value,
        entity_type="Loan",
        entity_id=loan.id,
        reason=(
            f"{method.value} {amount}" + (f" ref {reference}" if reference else "") + (f": {notes}" if notes else "")
            if is_staff
            else None
        ),
        company_id=loan.company_id,
    )
    try:
        session.commit()
    except IntegrityError:
        # Lost a race with another request recording the same reference.
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Payment reference {reference} was already recorded")
    session.refresh(transaction)
    return transaction
