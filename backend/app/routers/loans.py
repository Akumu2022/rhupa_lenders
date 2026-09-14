"""CLAUDE.md M4: loan products (seeded per company) + application submission.

Rule #6 / §10 Handoff 1: KYC-verified unlocks Apply, it never auto-submits —
the customer still chooses a product and amount, and the guard is enforced
here server-side, not just by hiding the button in the UI.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlmodel import Session, select

from ..audit import write_audit
from ..db import get_session
from ..db_helpers import get_or_404
from ..deps import get_current_user, require_role
from ..loan_delinquency import sync_loan_delinquency
from ..time_utils import as_utc
from ..models import (
    ApplicationStatus,
    AuditAction,
    KYCStatus,
    Loan,
    LoanApplication,
    LoanProduct,
    LoanStatus,
    Profile,
    RepaymentSchedule,
    Transaction,
    TransactionType,
    User,
    UserRole,
)
from ..schemas.loan import (
    CustomerCreditSummaryResponse,
    CustomerLoanResponse,
    LoanApplicationCreateRequest,
    LoanApplicationResponse,
    LoanProductResponse,
    RepaymentInstallmentResponse,
    RepaymentRequest,
    RepaymentResponse,
)

# M6 customer dashboard: a loan still counts against the customer's
# available credit until it's fully repaid. overdue/defaulted are still
# unpaid debt (CLAUDE.md §19) — they must count too, not just active.
_OUTSTANDING_LOAN_STATUSES = {LoanStatus.approved, LoanStatus.active, LoanStatus.overdue, LoanStatus.defaulted}

# CLAUDE.md §6: repayment stays open by default even once a loan has slipped
# into delinquency — don't trap a borrower who's trying to catch up.
_REPAYABLE_LOAN_STATUSES = {LoanStatus.active, LoanStatus.overdue, LoanStatus.defaulted}

router = APIRouter(tags=["loans"])


@router.get("/loan-products", response_model=list[LoanProductResponse])
def list_loan_products(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[LoanProduct]:
    return list(session.exec(select(LoanProduct).where(LoanProduct.is_active.is_(True))).all())


@router.post("/applications", response_model=LoanApplicationResponse, status_code=status.HTTP_201_CREATED)
def submit_application(
    body: LoanApplicationCreateRequest,
    session: Session = Depends(get_session),
    customer: User = Depends(require_role(UserRole.customer)),
) -> LoanApplication:
    profile = session.exec(select(Profile).where(Profile.user_id == customer.id)).first()
    # CLAUDE.md rule #6: no unverified customer can apply — enforced here,
    # not just by disabling the button in the UI.
    if profile is None or profile.kyc_status != KYCStatus.verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="KYC verification required before applying"
        )

    existing_pending = session.exec(
        select(LoanApplication).where(
            LoanApplication.customer_id == customer.id,
            LoanApplication.status == ApplicationStatus.pending,
        )
    ).first()
    if existing_pending is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already have a pending application")

    # session.get is tenant-scoped — a product id from another company comes
    # back None here, indistinguishable from "doesn't exist".
    product = session.get(LoanProduct, body.loan_product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan product not found")

    if body.amount_requested < product.min_amount or body.amount_requested > product.max_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Amount must be between {product.min_amount} and {product.max_amount}",
        )

    # CLAUDE.md §19 light exception monitoring: an existing_pending guard
    # above already stops "many pending applications at once" — this instead
    # catches many submit/reject cycles in a short window (probing behavior).
    past_day = datetime.now(timezone.utc) - timedelta(hours=24)
    prior_applications = session.exec(
        select(LoanApplication).where(LoanApplication.customer_id == customer.id)
    ).all()
    recent_count = sum(1 for a in prior_applications if as_utc(a.created_at) >= past_day)

    application = LoanApplication(
        customer_id=customer.id,
        loan_product_id=product.id,
        amount_requested=body.amount_requested,
        company_id=customer.company_id,  # from the authenticated customer, never the body
        status=ApplicationStatus.pending,
    )
    session.add(application)
    session.flush()

    if recent_count >= 2:  # this submission would be the 3rd within 24h
        write_audit(
            session,
            actor=customer,
            action=AuditAction.APPLICATION_RAPID_SUBMISSION.value,
            entity_type="LoanApplication",
            entity_id=application.id,
            reason=f"{recent_count + 1} applications submitted within 24 hours",
            company_id=customer.company_id,
            is_anomaly=True,
        )

    session.commit()
    session.refresh(application)
    return application


@router.get("/applications/me", response_model=list[LoanApplicationResponse])
def get_my_applications(
    session: Session = Depends(get_session),
    customer: User = Depends(require_role(UserRole.customer)),
) -> list[LoanApplication]:
    return list(
        session.exec(
            select(LoanApplication)
            .where(LoanApplication.customer_id == customer.id)
            .order_by(LoanApplication.created_at.desc())
        ).all()
    )


@router.get("/loans/me", response_model=CustomerCreditSummaryResponse)
def get_my_loans(
    session: Session = Depends(get_session),
    customer: User = Depends(require_role(UserRole.customer)),
) -> CustomerCreditSummaryResponse:
    """CLAUDE.md §9/M6: limit, active loans + status + balance, repayment
    schedule, and a simple standing indicator — never the raw score customers
    are never shown (rule #7)."""
    sync_loan_delinquency(session)
    active_products = session.exec(select(LoanProduct).where(LoanProduct.is_active.is_(True))).all()
    loan_limit = max((p.max_amount for p in active_products), default=Decimal("0.00"))

    loans = list(
        session.exec(
            select(Loan).where(Loan.customer_id == customer.id).order_by(Loan.created_at.desc())
        ).all()
    )

    outstanding_total = sum(
        (loan.outstanding_balance for loan in loans if loan.status in _OUTSTANDING_LOAN_STATUSES),
        Decimal("0.00"),
    )
    available_credit = max(loan_limit - outstanding_total, Decimal("0.00"))

    today = date.today()
    has_overdue_installment = False
    loan_responses: list[CustomerLoanResponse] = []
    for loan in loans:
        product = session.get(LoanProduct, loan.loan_product_id)
        schedule = list(
            session.exec(
                select(RepaymentSchedule)
                .where(RepaymentSchedule.loan_id == loan.id)
                .order_by(RepaymentSchedule.installment_number)
            ).all()
        )
        if loan.status in _OUTSTANDING_LOAN_STATUSES and any(
            not installment.is_paid and installment.due_date < today for installment in schedule
        ):
            has_overdue_installment = True

        loan_responses.append(
            CustomerLoanResponse(
                id=loan.id,
                loan_product_name=product.name if product is not None else "Loan",
                principal=loan.principal,
                interest_rate=loan.interest_rate,
                total_repayable=loan.total_repayable,
                penalties_accrued=loan.penalties_accrued,
                outstanding_balance=loan.outstanding_balance,
                status=loan.status.value,
                disbursed_at=loan.disbursed_at,
                created_at=loan.created_at,
                schedule=[
                    RepaymentInstallmentResponse(
                        id=installment.id,
                        installment_number=installment.installment_number,
                        due_date=installment.due_date,
                        amount_due=installment.amount_due,
                        amount_paid=installment.amount_paid,
                        principal_component=installment.principal_component,
                        interest_component=installment.interest_component,
                        is_paid=installment.is_paid,
                    )
                    for installment in schedule
                ],
            )
        )

    return CustomerCreditSummaryResponse(
        loan_limit=loan_limit,
        available_credit=available_credit,
        standing="attention_needed" if has_overdue_installment else "good_standing",
        loans=loan_responses,
    )


@router.post("/loans/{loan_id}/repay", response_model=RepaymentResponse)
def repay_loan(
    loan_id: int,
    body: RepaymentRequest,
    session: Session = Depends(get_session),
    customer: User = Depends(require_role(UserRole.customer)),
) -> RepaymentResponse:
    """CLAUDE.md M7: simulated repayment — on the suspension allow-list
    (§6/rule #10: repayment stays open for a suspended company so borrowers
    aren't trapped with debts they owe) and writes a ledger row (rule #9)."""
    loan = get_or_404(session, Loan, loan_id, detail="Loan not found")
    if loan.customer_id != customer.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found")

    if loan.status not in _REPAYABLE_LOAN_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Loan is not open for repayment")

    if body.amount > loan.outstanding_balance:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount exceeds outstanding balance")

    new_balance = loan.outstanding_balance - body.amount
    # A partial payment doesn't change delinquency status here — the next
    # sync_loan_delinquency() call (e.g. this same customer's next GET
    # /loans/me) recomputes overdue/active from the schedule, which is the
    # single source of truth for that (CLAUDE.md §19). A partially-paid
    # defaulted loan stays defaulted until fully repaid or an override.
    new_status = LoanStatus.repaid if new_balance <= Decimal("0.00") else loan.status

    # CLAUDE.md §14: compare-and-set on both status AND the balance being
    # decremented — the second concurrent repayment for the same loan sees a
    # rowcount of 0 and gets a 409 instead of silently double-spending it.
    result = session.execute(
        update(Loan)
        .where(
            Loan.id == loan_id,
            Loan.status == loan.status,
            Loan.outstanding_balance == loan.outstanding_balance,
        )
        .values(status=new_status, outstanding_balance=new_balance)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Loan balance changed, please retry")

    remaining = body.amount
    schedule = session.exec(
        select(RepaymentSchedule)
        .where(RepaymentSchedule.loan_id == loan_id, RepaymentSchedule.is_paid.is_(False))
        .order_by(RepaymentSchedule.installment_number)
    ).all()
    for installment in schedule:
        if remaining <= Decimal("0.00"):
            break
        applied = min(remaining, installment.amount_due - installment.amount_paid)
        installment.amount_paid += applied
        if installment.amount_paid >= installment.amount_due:
            installment.is_paid = True
        remaining -= applied
        session.add(installment)

    session.add(
        Transaction(
            loan_id=loan.id,
            customer_id=customer.id,
            company_id=customer.company_id,
            type=TransactionType.repayment,
            amount=body.amount,
        )
    )
    write_audit(
        session,
        actor=customer,
        action=AuditAction.LOAN_REPAY.value,
        entity_type="Loan",
        entity_id=loan_id,
        company_id=customer.company_id,
    )
    session.commit()

    return RepaymentResponse(
        loan_id=loan_id,
        amount_paid_now=body.amount,
        outstanding_balance=new_balance,
        status=new_status.value,
    )
