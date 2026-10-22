"""Releasing an approved loan — the one place it happens (CLAUDE.md §23, §28).

Used by the finance officer's manual "Disburse" button and by automatic
disbursement right after a final approval. Both go through the same compare-and-
set (rule #14), the same ledger row (rule #9) and the same audit trail; the only
difference is the actor: a person, or the system (`actor=None`).

Automatic disbursement is deliberately narrow: the company must have switched it
on AND set a maximum amount, the company must be active, and the loan must be at
or under that maximum. Anything else stays `approved` for a cashier/finance
officer, exactly as before. A gateway failure also leaves the loan `approved`.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlmodel import Session, select

from .audit import write_audit, write_system_audit
from .models import (
    AuditAction,
    Company,
    CompanyStatus,
    Loan,
    LoanStatus,
    Profile,
    Transaction,
    TransactionType,
    User,
)
from .payment_gateway import get_gateway


def disbursement_reference(loan: Loan) -> str:
    """Stable per loan: the idempotency key for the gateway and the ledger's
    unique reference, so the same loan can never be paid out twice."""
    return f"DISB-{loan.company_id:04d}-{loan.id:06d}"


def customer_phone(session: Session, customer_id: int) -> str:
    """Digits-only, country-code form (254700000000) as M-Pesa expects."""
    raw = session.exec(select(Profile.phone_number).where(Profile.user_id == customer_id)).first() or ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("0"):
        digits = "254" + digits[1:]
    return digits


def disburse_approved_loan(session: Session, loan: Loan, *, actor: Optional[User]) -> None:
    """Does not commit — the caller does. 409 if the loan is not awaiting
    disbursement; 502 if the payment gateway refuses (loan stays approved)."""
    if loan.status != LoanStatus.approved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Loan is not awaiting disbursement")

    reference = disbursement_reference(loan)
    result = get_gateway().send_money(
        idempotency_key=reference,
        amount=loan.principal,
        phone=customer_phone(session, loan.customer_id),
        narration=f"Loan {loan.id} disbursement",
    )
    if not result.ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Disbursement failed: {result.message}")

    # CLAUDE.md §14: compare-and-set, never a blind UPDATE.
    updated = session.execute(
        update(Loan)
        .where(Loan.id == loan.id, Loan.status == LoanStatus.approved)
        .values(status=LoanStatus.active, disbursed_at=datetime.now(timezone.utc))
    )
    if updated.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Loan is not awaiting disbursement")

    session.add(
        Transaction(
            loan_id=loan.id,
            customer_id=loan.customer_id,
            company_id=loan.company_id,
            type=TransactionType.disbursement,
            amount=loan.principal,
            reference=reference,
            notes=result.message,
        )
    )
    if actor is None:
        write_system_audit(
            session,
            action=AuditAction.LOAN_AUTO_DISBURSE.value,
            entity_type="Loan",
            entity_id=loan.id,
            reason=f"{reference} via {result.reference}",
            company_id=loan.company_id,
        )
    else:
        write_audit(
            session,
            actor=actor,
            action=AuditAction.LOAN_DISBURSE.value,
            entity_type="Loan",
            entity_id=loan.id,
            company_id=actor.company_id,
        )


def maybe_auto_disburse(session: Session, loan_id: int) -> bool:
    """Call right AFTER the approval has been committed. Never raises: the
    approval already stands, so any problem here is recorded and the loan simply
    waits for finance. Returns True only if the loan was disbursed."""
    loan = session.get(Loan, loan_id)
    if loan is None:
        return False
    company = session.get(Company, loan.company_id)
    if (
        company is None
        or company.status != CompanyStatus.active
        or not company.auto_disburse_enabled
        or company.auto_disburse_max_amount is None
        or loan.principal > company.auto_disburse_max_amount
    ):
        return False

    company_id = loan.company_id
    try:
        disburse_approved_loan(session, loan, actor=None)
        session.commit()
        return True
    except Exception as exc:  # noqa: BLE001 - see docstring
        session.rollback()
        detail = exc.detail if isinstance(exc, HTTPException) else f"{type(exc).__name__}: {exc}"
        write_system_audit(
            session,
            action=AuditAction.LOAN_AUTO_DISBURSE_FAILED.value,
            entity_type="Loan",
            entity_id=loan_id,
            reason=str(detail)[:500],
            company_id=company_id,
        )
        session.commit()
        return False
