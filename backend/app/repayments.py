"""The single place a repayment is applied to a loan — used by the
customer's own "repay now" and by staff recording money they received
(cash, M-Pesa, bank). One code path so the balance compare-and-set, the
schedule allocation, the ledger row, the receipt number and the audit entry
can never drift between the two.
"""

from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .audit import write_audit
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
        .values(status=new_status, outstanding_balance=new_balance)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Loan balance changed, please retry")

    remaining = amount
    schedule = session.exec(
        select(RepaymentSchedule)
        .where(RepaymentSchedule.loan_id == loan.id, RepaymentSchedule.is_paid.is_(False))
        .order_by(RepaymentSchedule.installment_number)
    ).all()
    for installment in schedule:
        if remaining <= _ZERO:
            break
        applied = min(remaining, installment.amount_due - installment.amount_paid)
        installment.amount_paid += applied
        if installment.amount_paid >= installment.amount_due:
            installment.is_paid = True
        remaining -= applied
        session.add(installment)

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
