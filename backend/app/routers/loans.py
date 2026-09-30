"""CLAUDE.md M4: loan products (seeded per company) + application submission.

Rule #6 / §10 Handoff 1: KYC-verified unlocks Apply, it never auto-submits —
the customer still chooses a product and amount, and the guard is enforced
here server-side, not just by hiding the button in the UI.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..audit import write_audit
from ..db import get_session
from ..db_helpers import get_or_404
from ..deps import get_current_user, require_role
from ..loan_analytics import in_scope, scope_for
from ..loan_delinquency import sync_loan_delinquency
from ..repayments import record_repayment
from ..time_utils import as_utc, business_today
from ..models import (
    PaymentMethod,
    ApplicationStatus,
    AuditAction,
    KYCStatus,
    Loan,
    LoanApplication,
    LoanProduct,
    LoanStatus,
    Profile,
    RepaymentSchedule,
    User,
    UserRole,
)
from ..schemas.loan import (
    ReceiptResponse,
    StaffPaymentRequest,
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


# CLAUDE.md §26 (M13): the two "still being decided" statuses — a customer
# may not submit a second application while one is anywhere in this chain.
_IN_REVIEW_APPLICATION_STATUSES = {
    ApplicationStatus.pending,
    ApplicationStatus.pending_branch_review,
    ApplicationStatus.pending_committee_review,
}

router = APIRouter(tags=["loans"])


@router.get("/loan-products", response_model=list[LoanProductResponse])
def list_loan_products(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[LoanProduct]:
    return list(session.exec(select(LoanProduct).where(LoanProduct.is_active.is_(True))).all())


def _create_application(
    session: Session, *, customer: User, product_id: int, amount_requested: Decimal, actor: User
) -> LoanApplication:
    """Shared by the customer's own self-service submission and the credit
    officer's assisted, on-behalf-of submission (CLAUDE.md §8: "the credit
    officer... prepares the application") — `customer` is always the
    applicant of record; `actor` is who's actually making this HTTP call and
    is only ever different from `customer` on the officer-assisted path."""
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
            LoanApplication.status.in_(_IN_REVIEW_APPLICATION_STATUSES),
        )
    ).first()
    if existing_pending is not None:
        detail = "You already have a pending application" if actor.id == customer.id else "This customer already has a pending application"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    # session.get is tenant-scoped — a product id from another company comes
    # back None here, indistinguishable from "doesn't exist".
    product = session.get(LoanProduct, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan product not found")

    if amount_requested < product.min_amount or amount_requested > product.max_amount:
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

    # CLAUDE.md §26: branch_id resolved server-side from the applicant's own
    # branch, never from the request body. A customer with no branch (a
    # self-signup with nothing to inherit from) skips branch review
    # entirely — there's no branch manager to route them to — and goes
    # straight to committee review.
    initial_status = (
        ApplicationStatus.pending_branch_review
        if customer.branch_id is not None
        else ApplicationStatus.pending_committee_review
    )
    application = LoanApplication(
        customer_id=customer.id,
        loan_product_id=product.id,
        amount_requested=amount_requested,
        company_id=customer.company_id,  # from the applicant, never the body
        branch_id=customer.branch_id,
        status=initial_status,
        prepared_by=actor.id if actor.id != customer.id else None,
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

    if actor.id != customer.id:
        # A staff action changing state gets its own audit entry in the same
        # change (CLAUDE.md §16) — the pure self-service path above writes
        # nothing extra, unchanged from before this helper existed.
        write_audit(
            session,
            actor=actor,
            action=AuditAction.APPLICATION_SUBMIT_FOR_CUSTOMER.value,
            entity_type="LoanApplication",
            entity_id=application.id,
            reason=f"submitted on behalf of {customer.email}",
            company_id=actor.company_id,
        )

    session.commit()
    session.refresh(application)
    return application


@router.post("/applications", response_model=LoanApplicationResponse, status_code=status.HTTP_201_CREATED)
def submit_application(
    body: LoanApplicationCreateRequest,
    session: Session = Depends(get_session),
    customer: User = Depends(require_role(UserRole.customer)),
) -> LoanApplication:
    return _create_application(
        session, customer=customer, product_id=body.loan_product_id, amount_requested=body.amount_requested, actor=customer
    )


@router.post("/customers/{customer_id}/applications", response_model=LoanApplicationResponse, status_code=status.HTTP_201_CREATED)
def submit_application_for_customer(
    customer_id: int,
    body: LoanApplicationCreateRequest,
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.credit_officer)),
) -> LoanApplication:
    """CLAUDE.md §8: the credit officer prepares the application on the
    customer's behalf — an assisted/in-branch path alongside (not replacing)
    customer self-service above. session.get is tenant-scoped (§5) already;
    the branch check below narrows further to "this officer's own branch",
    the same scope their customer list (`GET /customers`) already uses."""
    target = session.get(User, customer_id)
    if target is None or target.role != UserRole.customer or target.branch_id != officer.branch_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    return _create_application(
        session, customer=target, product_id=body.loan_product_id, amount_requested=body.amount_requested, actor=officer
    )


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

    today = business_today()
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

    transaction = record_repayment(
        session, loan=loan, amount=body.amount, actor=customer, method=PaymentMethod.customer_portal
    )
    session.refresh(loan)
    return RepaymentResponse(
        loan_id=loan_id,
        amount_paid_now=transaction.amount,
        outstanding_balance=loan.outstanding_balance,
        status=loan.status.value,
    )


@router.post("/loans/{loan_id}/payments", response_model=ReceiptResponse, status_code=status.HTTP_201_CREATED)
def record_staff_payment(
    loan_id: int,
    body: StaffPaymentRequest,
    session: Session = Depends(get_session),
    staff: User = Depends(require_role(UserRole.cashier_finance_officer, UserRole.credit_officer)),
) -> ReceiptResponse:
    """Record money a staff member received for a loan (cash at the branch,
    M-Pesa to the company, bank deposit). Borrowers mostly pay this way, not
    through the customer portal. Same balance/schedule/ledger/audit path as
    self-service repayment (app/repayments.py); an M-Pesa or bank reference
    can only ever be recorded once per company.

    Credit officers are limited to loans in their own branch (the same scope
    as their loans list); the cashier is company-wide. On the suspension
    allow-list: a suspended company's borrowers can still pay (CLAUDE.md §6).
    """
    loan = get_or_404(session, Loan, loan_id, detail="Loan not found")
    application = session.get(LoanApplication, loan.application_id)
    if application is None or not in_scope(application, scope_for(staff)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found")

    transaction = record_repayment(
        session,
        loan=loan,
        amount=body.amount,
        actor=staff,
        method=PaymentMethod(body.method),
        reference=body.reference,
        notes=body.notes,
    )
    session.refresh(loan)
    customer = session.get(User, loan.customer_id)
    product = session.get(LoanProduct, loan.loan_product_id)
    return ReceiptResponse(
        transaction_id=transaction.id,
        receipt_number=transaction.receipt_number,
        loan_id=loan.id,
        application_id=loan.application_id,
        customer_full_name=customer.full_name,
        loan_product_name=product.name,
        amount=transaction.amount,
        method=transaction.method.value,
        reference=transaction.reference,
        notes=transaction.notes,
        received_by_name=staff.full_name,
        received_at=transaction.created_at,
        outstanding_balance_after=loan.outstanding_balance,
        loan_status=loan.status.value,
    )
