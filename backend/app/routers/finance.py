"""CLAUDE.md §28/§30 (M14/M17): cashier/finance officer — executes
disbursement (moved here from credit_officer, the one concrete permission
change §28 calls for) and owns the expense ledger + derived financial
views. Disbursement itself is still fully simulated (§1) — no real
gateway — but still writes a ledger + audit row (rule #9).
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlmodel import Session, select

from ..audit import write_audit
from ..db import get_session
from ..db_helpers import get_or_404
from ..deps import require_role
from ..models import (
    AuditAction,
    ExpenseEntry,
    Loan,
    LoanProduct,
    LoanStatus,
    Transaction,
    TransactionType,
    User,
    UserRole,
)
from ..portfolio import compute_report
from ..schemas.credit import DisbursementResponse, LoanResponse, PendingDisbursementResponse
from ..schemas.finance import ExpenseCreateRequest, ExpenseResponse, FinancialsResponse
from ..schemas.reports import ReportResponse

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/disbursements", response_model=list[PendingDisbursementResponse])
def get_pending_disbursements(
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.cashier_finance_officer)),
) -> list[PendingDisbursementResponse]:
    rows = session.exec(
        select(Loan, User, LoanProduct)
        .join(User, User.id == Loan.customer_id)
        .join(LoanProduct, LoanProduct.id == Loan.loan_product_id)
        .where(Loan.status == LoanStatus.approved)
        .order_by(Loan.created_at)
    ).all()
    return [
        PendingDisbursementResponse(
            id=loan.id,
            customer_full_name=customer.full_name,
            customer_email=customer.email,
            loan_product_name=product.name,
            principal=loan.principal,
            total_repayable=loan.total_repayable,
            created_at=loan.created_at,
        )
        for loan, customer, product in rows
    ]


@router.post("/loans/{loan_id}/disburse", response_model=DisbursementResponse)
def disburse_loan(
    loan_id: int,
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.cashier_finance_officer)),
) -> DisbursementResponse:
    """CLAUDE.md M7/§28: simulated disbursement — no real money moves, but it
    still writes a ledger row (rule #9) and is on the suspension block-list,
    not the allow-list (§6: "new applications / disbursements: stopped")."""
    loan = get_or_404(session, Loan, loan_id, detail="Loan not found")

    now = datetime.now(timezone.utc)
    # CLAUDE.md §14: compare-and-set, never a blind UPDATE.
    result = session.execute(
        update(Loan)
        .where(Loan.id == loan_id, Loan.status == LoanStatus.approved)
        .values(status=LoanStatus.active, disbursed_at=now)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Loan is not awaiting disbursement")

    session.add(
        Transaction(
            loan_id=loan.id,
            customer_id=loan.customer_id,
            company_id=loan.company_id,
            type=TransactionType.disbursement,
            amount=loan.principal,
        )
    )
    write_audit(
        session,
        actor=officer,
        action=AuditAction.LOAN_DISBURSE.value,
        entity_type="Loan",
        entity_id=loan_id,
        company_id=officer.company_id,
    )
    session.commit()

    session.refresh(loan)
    return DisbursementResponse(
        loan=LoanResponse(
            id=loan.id,
            application_id=loan.application_id,
            principal=loan.principal,
            interest_rate=loan.interest_rate,
            total_repayable=loan.total_repayable,
            penalties_accrued=loan.penalties_accrued,
            outstanding_balance=loan.outstanding_balance,
            status=loan.status.value,
            disbursed_at=loan.disbursed_at,
        )
    )


@router.post("/expenses", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_expense(
    body: ExpenseCreateRequest,
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.cashier_finance_officer)),
) -> ExpenseResponse:
    expense = ExpenseEntry(
        company_id=officer.company_id,
        branch_id=body.branch_id,
        category=body.category,
        amount=body.amount,
        description=body.description,
        created_by=officer.id,
    )
    session.add(expense)
    session.flush()

    write_audit(
        session,
        actor=officer,
        action=AuditAction.EXPENSE_CREATE.value,
        entity_type="ExpenseEntry",
        entity_id=expense.id,
        reason=f"{body.category.value}: {body.amount}",
        company_id=officer.company_id,
    )
    session.commit()
    session.refresh(expense)
    return ExpenseResponse(
        id=expense.id,
        category=expense.category,
        amount=expense.amount,
        description=expense.description,
        branch_id=expense.branch_id,
        created_by_name=officer.full_name,
        created_at=expense.created_at,
    )


_FINANCIALS_WINDOW_DAYS = 30


@router.get("/financials", response_model=FinancialsResponse)
def get_financials(
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.cashier_finance_officer)),
) -> FinancialsResponse:
    """CLAUDE.md §30: cashbook-style view over the trailing 30 days, derived
    read-only from Transaction (income) + ExpenseEntry (expenses) — never a
    second ledger."""
    window_start = datetime.now(timezone.utc) - timedelta(days=_FINANCIALS_WINDOW_DAYS)

    txn_rows = session.exec(
        select(Transaction.type, Transaction.amount).where(Transaction.created_at >= window_start)
    ).all()
    total_repayment_income = sum((r.amount for r in txn_rows if r.type == TransactionType.repayment), Decimal("0.00"))
    total_penalty_income = sum((r.amount for r in txn_rows if r.type == TransactionType.penalty), Decimal("0.00"))
    total_disbursed = sum((r.amount for r in txn_rows if r.type == TransactionType.disbursement), Decimal("0.00"))

    expense_rows = session.exec(
        select(ExpenseEntry)
        .where(ExpenseEntry.created_at >= window_start)
        .order_by(ExpenseEntry.created_at.desc())
    ).all()
    total_expenses = sum((e.amount for e in expense_rows), Decimal("0.00"))

    expense_authors = {}
    recent_expenses = []
    for e in expense_rows[:20]:
        if e.created_by not in expense_authors:
            author = session.get(User, e.created_by)
            expense_authors[e.created_by] = author.full_name if author else "Unknown"
        recent_expenses.append(
            ExpenseResponse(
                id=e.id,
                category=e.category,
                amount=e.amount,
                description=e.description,
                branch_id=e.branch_id,
                created_by_name=expense_authors[e.created_by],
                created_at=e.created_at,
            )
        )

    return FinancialsResponse(
        period_start=window_start.date().isoformat(),
        total_repayment_income=total_repayment_income,
        total_penalty_income=total_penalty_income,
        total_disbursed=total_disbursed,
        total_expenses=total_expenses,
        net=total_repayment_income + total_penalty_income - total_expenses,
        recent_expenses=recent_expenses,
    )


@router.get("/reports", response_model=ReportResponse)
def get_finance_report(
    start_date: date,
    end_date: date,
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.cashier_finance_officer)),
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
