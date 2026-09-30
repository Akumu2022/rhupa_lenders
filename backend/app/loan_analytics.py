"""Shared, role-scoped loan analytics — one computation behind every staff
dashboard (credit officer, branch manager, finance, management, system
administrator), so the same number means the same thing on every screen.

Scope is always derived server-side from the authenticated user (never from
the request): branch-scoped roles (credit_officer, branch_manager) see their
own branch; company-wide roles see the whole company. company_id isolation is
the central tenant listener's job (CLAUDE.md §5) — nothing here filters on it.
branch_id / prepared_by are ordinary hand filters (§5's explicit asymmetry).

Money is Decimal end to end (rule #13): sums are done in Python over narrow
row sets, never SQL SUM() on Numeric, matching app/portfolio.py.

Balance split convention (same as app/portfolio.py::_principal_repaid):
payments are allocated principal first, then base interest, then penalties.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import or_
from sqlmodel import Session, select

from .loan_delinquency import sync_loan_delinquency
from .models import (
    ApplicationReviewStage,
    ApplicationStatus,
    AuditAction,
    AuditLog,
    Branch,
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
from .time_utils import as_utc, business_date, business_today

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

BRANCH_SCOPED_ROLES = {UserRole.credit_officer, UserRole.branch_manager}

IN_REVIEW_STATUSES = {
    ApplicationStatus.pending,
    ApplicationStatus.pending_branch_review,
    ApplicationStatus.pending_committee_review,
}
OUTSTANDING_LOAN_STATUSES = {LoanStatus.active, LoanStatus.overdue, LoanStatus.defaulted}
AT_RISK_LOAN_STATUSES = {LoanStatus.overdue, LoanStatus.defaulted}
DISBURSED_LOAN_STATUSES = OUTSTANDING_LOAN_STATUSES | {LoanStatus.repaid}

# Lifecycle stage of one application, combining its own status with its
# loan's status — the single vocabulary the dashboards, lists, and drill-downs
# all use. Order is the pipeline order.
STAGES = ["in_review", "awaiting_disbursement", "active", "overdue", "defaulted", "repaid", "rejected"]
# "Sorted" = got a yes and moved on (everything past approval).
SORTED_STAGES = {"awaiting_disbursement", "active", "overdue", "defaulted", "repaid"}

# CLAUDE.md §29: the client's exact aging buckets.
AGING_BUCKETS = ["current", "1-7", "8-30", "31-60", "61-90", "90+"]


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        return ZERO
    return (numerator / denominator * Decimal("100")).quantize(CENT)


def aging_bucket(days_past_due: int) -> str:
    if days_past_due <= 0:
        return "current"
    if days_past_due <= 7:
        return "1-7"
    if days_past_due <= 30:
        return "8-30"
    if days_past_due <= 60:
        return "31-60"
    if days_past_due <= 90:
        return "61-90"
    return "90+"


def application_stage(application: LoanApplication, loan: Optional[Loan]) -> str:
    if application.status == ApplicationStatus.rejected:
        return "rejected"
    if application.status in IN_REVIEW_STATUSES:
        return "in_review"
    if loan is None:
        # Approved but no loan row yet — can't happen through the normal
        # flow; treat as awaiting disbursement rather than inventing a stage.
        return "awaiting_disbursement"
    return {
        LoanStatus.approved: "awaiting_disbursement",
        LoanStatus.active: "active",
        LoanStatus.overdue: "overdue",
        LoanStatus.defaulted: "defaulted",
        LoanStatus.repaid: "repaid",
    }[loan.status]


@dataclass
class BalanceSplit:
    principal: Decimal
    interest: Decimal
    penalties: Decimal
    repaid: Decimal


def balance_split(loan: Loan) -> BalanceSplit:
    """CLAUDE.md §23 3-way breakdown of what's still owed."""
    interest_total = loan.total_repayable - loan.principal
    owed_total = loan.total_repayable + loan.penalties_accrued
    repaid = max(owed_total - loan.outstanding_balance, ZERO)
    principal_repaid = min(loan.principal, repaid)
    interest_repaid = min(interest_total, max(repaid - loan.principal, ZERO))
    principal_out = loan.principal - principal_repaid
    interest_out = interest_total - interest_repaid
    penalties_out = max(loan.outstanding_balance - principal_out - interest_out, ZERO)
    return BalanceSplit(principal=principal_out, interest=interest_out, penalties=penalties_out, repaid=repaid)


def installment_remaining(installment: RepaymentSchedule) -> Decimal:
    return ZERO if installment.is_paid else max(installment.amount_due - installment.amount_paid, ZERO)


def installment_state(installment: RepaymentSchedule, today: date) -> str:
    if installment.is_paid:
        return "paid"
    if installment.due_date < today:
        return "overdue"
    if installment.amount_paid > 0:
        return "partial"
    if installment.due_date == today:
        return "due_today"
    return "upcoming"


# --------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------


@dataclass
class Scope:
    branch_id: Optional[int] = None
    # A branch-scoped role whose account has no branch (legacy accounts
    # created before M10 made branch_id required). They see only the
    # equally-unassigned applications in their company, never the whole
    # company: narrowing to "branch_id IS NULL" rather than widening.
    unassigned: bool = False
    prepared_by: Optional[int] = None

    @property
    def label(self) -> str:
        if self.prepared_by is not None:
            return "mine"
        if self.unassigned:
            return "unassigned"
        return "branch" if self.branch_id is not None else "company"


def scope_for(user: User, *, mine: bool = False) -> Scope:
    scope = Scope(prepared_by=user.id if mine and user.role == UserRole.credit_officer else None)
    if user.role in BRANCH_SCOPED_ROLES:
        if user.branch_id is None:
            scope.unassigned = True
        else:
            scope.branch_id = user.branch_id
    return scope


def _scoped(query, scope: Scope):
    """Assumes LoanApplication is part of the query (selected or joined)."""
    if scope.unassigned:
        query = query.where(LoanApplication.branch_id.is_(None))
    elif scope.branch_id is not None:
        query = query.where(LoanApplication.branch_id == scope.branch_id)
    if scope.prepared_by is not None:
        query = query.where(LoanApplication.prepared_by == scope.prepared_by)
    return query


def in_scope(application: LoanApplication, scope: Scope) -> bool:
    if scope.unassigned and application.branch_id is not None:
        return False
    if scope.branch_id is not None and application.branch_id != scope.branch_id:
        return False
    if scope.prepared_by is not None and application.prepared_by != scope.prepared_by:
        return False
    return True


@dataclass
class _Book:
    applications: list[LoanApplication]
    loans: list[Loan]
    installments: list[RepaymentSchedule]
    transactions: list[Transaction]


def _load_book(session: Session, scope: Scope) -> _Book:
    applications = list(session.exec(_scoped(select(LoanApplication), scope)).all())
    loans = list(
        session.exec(
            _scoped(select(Loan).join(LoanApplication, LoanApplication.id == Loan.application_id), scope)
        ).all()
    )
    installments = list(
        session.exec(
            _scoped(
                select(RepaymentSchedule)
                .join(Loan, Loan.id == RepaymentSchedule.loan_id)
                .join(LoanApplication, LoanApplication.id == Loan.application_id),
                scope,
            )
        ).all()
    )
    transactions = list(
        session.exec(
            _scoped(
                select(Transaction)
                .join(Loan, Loan.id == Transaction.loan_id)
                .join(LoanApplication, LoanApplication.id == Loan.application_id),
                scope,
            )
        ).all()
    )
    return _Book(applications, loans, installments, transactions)


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------


def _in_range(value: Optional[datetime], start: date, end: date) -> bool:
    if value is None:
        return False
    return start <= business_date(value) <= end


def _stage_counts(applications: Iterable[LoanApplication], loan_by_app: dict[int, Loan]) -> list[dict]:
    counts = {stage: {"stage": stage, "count": 0, "amount": ZERO} for stage in STAGES}
    for application in applications:
        loan = loan_by_app.get(application.id)
        bucket = counts[application_stage(application, loan)]
        bucket["count"] += 1
        bucket["amount"] += loan.principal if loan is not None else application.amount_requested
    return list(counts.values())


def _series_periods(start: date, end: date) -> tuple[str, list[date]]:
    if (end - start).days <= 62:
        return "day", [start + timedelta(days=i) for i in range((end - start).days + 1)]
    periods = []
    cursor = start.replace(day=1)
    while cursor <= end:
        periods.append(cursor)
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return "month", periods


def compute_dashboard(
    session: Session,
    scope: Scope,
    *,
    start: date,
    end: date,
    include_names: bool,
    today: Optional[date] = None,
) -> dict:
    sync_loan_delinquency(session)
    today = today or business_today()
    book = _load_book(session, scope)
    loan_by_app = {loan.application_id: loan for loan in book.loans}
    loan_by_id = {loan.id: loan for loan in book.loans}

    # ---- live queues (a queue has no date range — it's "right now") ----
    in_review = [a for a in book.applications if a.status in IN_REVIEW_STATUSES]
    awaiting_disbursement = [l for l in book.loans if l.status == LoanStatus.approved]

    # ---- pipeline: applications submitted in the range, by stage ----
    apps_in_range = [a for a in book.applications if _in_range(a.created_at, start, end)]

    # ---- flows in range ----
    disbursed_in_range = [l for l in book.loans if _in_range(l.disbursed_at, start, end)]
    repayments_in_range = [
        t for t in book.transactions if t.type == TransactionType.repayment and _in_range(t.created_at, start, end)
    ]
    penalties_in_range = [
        t for t in book.transactions if t.type == TransactionType.penalty and _in_range(t.created_at, start, end)
    ]

    # Collection rate: of what fell due in the range (up to today), how much
    # has been paid.
    due_window_end = min(end, today)
    due_in_range = [i for i in book.installments if start <= i.due_date <= due_window_end]
    due_amount = sum((i.amount_due for i in due_in_range), ZERO)
    paid_against_due = sum((min(i.amount_paid, i.amount_due) for i in due_in_range), ZERO)

    # ---- portfolio snapshot (as of now) ----
    outstanding = [l for l in book.loans if l.status in OUTSTANDING_LOAN_STATUSES]
    splits = {l.id: balance_split(l) for l in book.loans if l.status in DISBURSED_LOAN_STATUSES}
    outstanding_principal = sum((splits[l.id].principal for l in outstanding), ZERO)
    at_risk_principal = sum((splits[l.id].principal for l in outstanding if l.status in AT_RISK_LOAN_STATUSES), ZERO)
    disbursed_book = [l for l in book.loans if l.status in DISBURSED_LOAN_STATUSES]
    book_owed = sum((l.total_repayable + l.penalties_accrued for l in disbursed_book), ZERO)
    book_repaid = sum((splits[l.id].repaid for l in disbursed_book), ZERO)

    # ---- due dates ----
    open_installments = [
        i for i in book.installments
        if not i.is_paid and loan_by_id.get(i.loan_id) is not None and loan_by_id[i.loan_id].status in OUTSTANDING_LOAN_STATUSES
    ]
    due_today = [
        i for i in book.installments
        if i.due_date == today and loan_by_id.get(i.loan_id) is not None and loan_by_id[i.loan_id].status in DISBURSED_LOAN_STATUSES
    ]
    overdue_installments = [i for i in open_installments if i.due_date < today]
    upcoming = []
    for offset in range(7):
        day = today + timedelta(days=offset)
        day_items = [i for i in open_installments if i.due_date == day]
        upcoming.append({"date": day, "count": len(day_items), "amount": sum((installment_remaining(i) for i in day_items), ZERO)})
    next_30 = [i for i in open_installments if today < i.due_date <= today + timedelta(days=30)]

    # ---- aging (by loan, from its earliest unpaid overdue installment) ----
    earliest_overdue: dict[int, date] = {}
    for i in overdue_installments:
        if i.loan_id not in earliest_overdue or i.due_date < earliest_overdue[i.loan_id]:
            earliest_overdue[i.loan_id] = i.due_date
    aging = {b: {"bucket": b, "count": 0, "amount": ZERO} for b in AGING_BUCKETS}
    for loan in outstanding:
        dpd = (today - earliest_overdue[loan.id]).days if loan.id in earliest_overdue else 0
        entry = aging[aging_bucket(dpd)]
        entry["count"] += 1
        entry["amount"] += loan.outstanding_balance

    # ---- time series ----
    granularity, periods = _series_periods(start, end)

    def _period_key(value: datetime) -> date:
        d = business_date(value)
        return d if granularity == "day" else d.replace(day=1)

    series = {p: {"period": p, "disbursed": ZERO, "collected": ZERO, "due": ZERO} for p in periods}
    for loan in disbursed_in_range:
        key = _period_key(loan.disbursed_at)
        if key in series:
            series[key]["disbursed"] += loan.principal
    for txn in repayments_in_range:
        key = _period_key(txn.created_at)
        if key in series:
            series[key]["collected"] += txn.amount
    for inst in book.installments:
        if start <= inst.due_date <= end:
            key = inst.due_date if granularity == "day" else inst.due_date.replace(day=1)
            if key in series:
                series[key]["due"] += inst.amount_due

    result = {
        "start": start,
        "end": end,
        "as_of": today,
        "scope": scope.label,
        "queues": {
            "in_review_count": len(in_review),
            "in_review_amount": sum((a.amount_requested for a in in_review), ZERO),
            "awaiting_disbursement_count": len(awaiting_disbursement),
            "awaiting_disbursement_amount": sum((l.principal for l in awaiting_disbursement), ZERO),
        },
        "pipeline": _stage_counts(apps_in_range, loan_by_app),
        "pipeline_all_time": _stage_counts(book.applications, loan_by_app),
        "flows": {
            "disbursed_count": len(disbursed_in_range),
            "disbursed_amount": sum((l.principal for l in disbursed_in_range), ZERO),
            "collected_count": len(repayments_in_range),
            "collected_amount": sum((t.amount for t in repayments_in_range), ZERO),
            "penalties_charged": sum((t.amount for t in penalties_in_range), ZERO),
            "due_amount": due_amount,
            "paid_against_due": paid_against_due,
            "collection_rate_pct": _pct(paid_against_due, due_amount),
        },
        "portfolio": {
            "active_loans": sum(1 for l in book.loans if l.status == LoanStatus.active),
            "overdue_loans": sum(1 for l in book.loans if l.status == LoanStatus.overdue),
            "defaulted_loans": sum(1 for l in book.loans if l.status == LoanStatus.defaulted),
            "repaid_loans": sum(1 for l in book.loans if l.status == LoanStatus.repaid),
            "active_borrowers": len({l.customer_id for l in outstanding}),
            "total_disbursed_all_time": sum((l.principal for l in disbursed_book), ZERO),
            "total_repaid_all_time": book_repaid,
            "outstanding_principal": outstanding_principal,
            "outstanding_interest": sum((splits[l.id].interest for l in outstanding), ZERO),
            "outstanding_penalties": sum((splits[l.id].penalties for l in outstanding), ZERO),
            "outstanding_total": sum((l.outstanding_balance for l in outstanding), ZERO),
            "arrears_amount": sum((installment_remaining(i) for i in overdue_installments), ZERO),
            "repayment_progress_pct": _pct(book_repaid, book_owed),
            "par_pct": _pct(at_risk_principal, outstanding_principal),
        },
        "due": {
            "today_count": len(due_today),
            "today_amount": sum((i.amount_due for i in due_today), ZERO),
            "today_collected": sum((min(i.amount_paid, i.amount_due) for i in due_today), ZERO),
            "today_paid": sum(1 for i in due_today if i.is_paid),
            "today_partial": sum(1 for i in due_today if not i.is_paid and i.amount_paid > 0),
            "today_unpaid": sum(1 for i in due_today if not i.is_paid and i.amount_paid == 0),
            "overdue_installments": len(overdue_installments),
            "next_7_days": upcoming,
            "next_30_days_amount": sum((installment_remaining(i) for i in next_30), ZERO),
            "next_30_days_count": len(next_30),
        },
        "aging": list(aging.values()),
        "granularity": granularity,
        "series": list(series.values()),
        "due_list": [],
    }

    # Named, actionable due list — never for aggregate-only roles (§9:
    # management sees no individual PII on headline screens).
    if include_names:
        watch = sorted(
            (i for i in open_installments if i.due_date <= today + timedelta(days=7)),
            key=lambda i: i.due_date,
        )[:50]
        customer_ids = {loan_by_id[i.loan_id].customer_id for i in watch}
        names = (
            {u.id: u.full_name for u in session.exec(select(User).where(User.id.in_(customer_ids))).all()}
            if customer_ids
            else {}
        )
        result["due_list"] = [
            {
                "application_id": loan_by_id[i.loan_id].application_id,
                "loan_id": i.loan_id,
                "customer_full_name": names.get(loan_by_id[i.loan_id].customer_id, "—"),
                "installment_number": i.installment_number,
                "due_date": i.due_date,
                "amount_remaining": installment_remaining(i),
                "days_past_due": max((today - i.due_date).days, 0),
                "state": installment_state(i, today),
            }
            for i in watch
        ]
    return result


# --------------------------------------------------------------------------
# Applications list (every stage, not just in-review)
# --------------------------------------------------------------------------


def list_applications(session: Session, scope: Scope, *, today: Optional[date] = None) -> list[dict]:
    sync_loan_delinquency(session)
    today = today or business_today()
    rows = session.exec(
        _scoped(
            select(LoanApplication, User, LoanProduct, Loan)
            .join(User, User.id == LoanApplication.customer_id)
            .join(LoanProduct, LoanProduct.id == LoanApplication.loan_product_id)
            .outerjoin(Loan, Loan.application_id == LoanApplication.id),
            scope,
        ).order_by(LoanApplication.created_at.desc())
    ).all()

    loan_ids = [loan.id for _, _, _, loan in rows if loan is not None]
    open_by_loan: dict[int, list[RepaymentSchedule]] = {}
    if loan_ids:
        for inst in session.exec(
            select(RepaymentSchedule).where(RepaymentSchedule.loan_id.in_(loan_ids), RepaymentSchedule.is_paid.is_(False))
        ).all():
            open_by_loan.setdefault(inst.loan_id, []).append(inst)

    preparer_ids = {a.prepared_by for a, _, _, _ in rows if a.prepared_by is not None}
    preparers = (
        {u.id: u.full_name for u in session.exec(select(User).where(User.id.in_(preparer_ids))).all()}
        if preparer_ids
        else {}
    )

    result = []
    for application, customer, product, loan in rows:
        open_items = open_by_loan.get(loan.id, []) if loan is not None else []
        next_due = min((i.due_date for i in open_items), default=None)
        result.append(
            {
                "id": application.id,
                "customer_id": customer.id,
                "customer_full_name": customer.full_name,
                "customer_email": customer.email,
                "loan_product_name": product.name,
                "amount_requested": application.amount_requested,
                "status": application.status.value,
                "loan_id": loan.id if loan is not None else None,
                "loan_status": loan.status.value if loan is not None else None,
                "stage": application_stage(application, loan),
                "prepared_by_name": preparers.get(application.prepared_by) if application.prepared_by else None,
                "created_at": application.created_at,
                "reviewed_at": application.reviewed_at,
                "review_notes": application.review_notes,
                "principal": loan.principal if loan is not None else None,
                "outstanding_balance": loan.outstanding_balance if loan is not None else None,
                "disbursed_at": loan.disbursed_at if loan is not None else None,
                "next_due_date": next_due,
                "days_past_due": max((today - next_due).days, 0) if next_due is not None else 0,
            }
        )
    return result


# --------------------------------------------------------------------------
# Timeline (the full movement history of one application/loan)
# --------------------------------------------------------------------------


def build_timeline(session: Session, application: LoanApplication, *, today: Optional[date] = None) -> dict:
    sync_loan_delinquency(session)
    today = today or business_today()
    customer = session.get(User, application.customer_id)
    product = session.get(LoanProduct, application.loan_product_id)
    branch = session.get(Branch, application.branch_id) if application.branch_id else None
    profile = session.exec(select(Profile).where(Profile.user_id == application.customer_id)).first()
    loan = session.exec(select(Loan).where(Loan.application_id == application.id)).first()
    stages = session.exec(
        select(ApplicationReviewStage)
        .where(ApplicationReviewStage.application_id == application.id)
        .order_by(ApplicationReviewStage.decided_at)
    ).all()

    audit_filters = [
        (AuditLog.entity_type == "LoanApplication") & (AuditLog.entity_id == application.id),
        (AuditLog.entity_type == "User") & (AuditLog.entity_id == application.customer_id),
    ]
    if profile is not None:
        audit_filters.append((AuditLog.entity_type == "Profile") & (AuditLog.entity_id == profile.id))
    if loan is not None:
        audit_filters.append((AuditLog.entity_type == "Loan") & (AuditLog.entity_id == loan.id))
    audits = session.exec(select(AuditLog).where(or_(*audit_filters)).order_by(AuditLog.created_at)).all()

    user_ids = {s.actor_id for s in stages} | {a.actor_id for a in audits if a.actor_id}
    for uid in (application.prepared_by, application.reviewed_by, profile.reviewed_by if profile else None):
        if uid:
            user_ids.add(uid)
    names = (
        {u.id: u.full_name for u in session.exec(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    )

    events: list[dict] = []

    def add(at, kind, title, *, tone="neutral", actor_id=None, detail=None, amount=None):
        if at is None:
            return
        events.append(
            {
                "at": as_utc(at),
                "kind": kind,
                "title": title,
                "tone": tone,
                "actor_name": names.get(actor_id) if actor_id else None,
                "detail": detail,
                "amount": amount,
            }
        )

    by_action = {}
    for entry in audits:
        by_action.setdefault(entry.action, []).append(entry)

    register = by_action.get(AuditAction.CUSTOMER_REGISTER.value, [])
    if register:
        add(register[0].created_at, "registered", "Customer registered", actor_id=register[0].actor_id)
    elif profile is not None:
        add(profile.created_at, "registered", "Customer profile submitted")

    if profile is not None and profile.reviewed_at is not None and profile.kyc_status.value != "pending":
        verified = profile.kyc_status.value == "verified"
        add(
            profile.reviewed_at,
            "kyc",
            "KYC verified" if verified else "KYC rejected",
            tone="success" if verified else "danger",
            actor_id=profile.reviewed_by,
        )
    for entry in by_action.get(AuditAction.KYC_OVERRIDE.value, []):
        add(entry.created_at, "override", "KYC decision overridden", tone="warning", actor_id=entry.actor_id, detail=entry.reason)

    add(
        application.created_at,
        "submitted",
        f"Applied for {product.name if product else 'loan'}",
        actor_id=application.prepared_by,
        detail=None if application.prepared_by else "Self-service application",
        amount=application.amount_requested,
    )

    stage_label = {"branch_review": "Branch manager", "committee_review": "Committee"}
    decision_label = {"approve": "approved", "reject": "rejected", "escalate": "escalated to committee"}
    decision_tone = {"approve": "success", "reject": "danger", "escalate": "warning"}
    for s in stages:
        add(
            s.decided_at,
            "review",
            f"{stage_label.get(s.stage.value, s.stage.value)} {decision_label.get(s.decision.value, s.decision.value)}",
            tone=decision_tone.get(s.decision.value, "neutral"),
            actor_id=s.actor_id,
            detail=s.comments,
        )
    if not stages and application.reviewed_at is not None and application.status in (
        ApplicationStatus.approved,
        ApplicationStatus.rejected,
    ):
        approved = application.status == ApplicationStatus.approved
        add(
            application.reviewed_at,
            "review",
            "Application approved" if approved else "Application rejected",
            tone="success" if approved else "danger",
            actor_id=application.reviewed_by,
            detail=application.review_notes,
        )
    for entry in by_action.get(AuditAction.APPLICATION_OVERRIDE.value, []):
        add(entry.created_at, "override", "Decision overridden by administrator", tone="warning", actor_id=entry.actor_id, detail=entry.reason)

    schedule: list[dict] = []
    loan_summary = None
    if loan is not None:
        add(loan.created_at, "loan_created", "Loan created — awaiting disbursement", amount=loan.principal)
        disburse_audit = by_action.get(AuditAction.LOAN_DISBURSE.value, [])
        add(
            loan.disbursed_at,
            "disbursed",
            "Disbursed",
            tone="info",
            actor_id=disburse_audit[0].actor_id if disburse_audit else None,
            amount=loan.principal,
        )

        transactions = session.exec(
            select(Transaction).where(Transaction.loan_id == loan.id).order_by(Transaction.created_at)
        ).all()
        repayments = [t for t in transactions if t.type == TransactionType.repayment]
        extra_ids = {t.recorded_by for t in repayments if t.recorded_by} - set(names)
        if extra_ids:
            names.update({u.id: u.full_name for u in session.exec(select(User).where(User.id.in_(extra_ids))).all()})
        if customer is not None:
            names.setdefault(customer.id, customer.full_name)
        method_label = {"customer_portal": "Customer portal", "cash": "Cash", "mpesa": "M-Pesa", "bank": "Bank"}
        for txn in repayments:
            parts = [method_label.get(txn.method.value, txn.method.value)] if txn.method else []
            if txn.reference:
                parts.append(txn.reference)
            if txn.receipt_number:
                parts.append(f"Receipt {txn.receipt_number}")
            if txn.notes:
                parts.append(txn.notes)
            add(
                txn.created_at,
                "repayment",
                "Payment received" if txn.recorded_by else "Repayment received",
                tone="success",
                actor_id=txn.recorded_by or txn.customer_id,
                detail=" · ".join(parts) or None,
                amount=txn.amount,
            )
        penalties = [t for t in transactions if t.type == TransactionType.penalty]
        if penalties:
            total_penalty = sum((t.amount for t in penalties), ZERO)
            first = business_date(penalties[0].created_at)
            last = business_date(penalties[-1].created_at)
            add(
                penalties[-1].created_at,
                "penalty",
                f"Late penalties charged ({len(penalties)} charge{'s' if len(penalties) != 1 else ''})",
                tone="danger",
                detail=f"{first.isoformat()} to {last.isoformat()}" if first != last else first.isoformat(),
                amount=total_penalty,
            )
        for entry in by_action.get(AuditAction.LOAN_MARK_DEFAULTED.value, []):
            add(entry.created_at, "defaulted", "Marked as defaulted", tone="danger", actor_id=entry.actor_id, detail=entry.reason)
        if loan.status == LoanStatus.repaid and repayments:
            add(repayments[-1].created_at, "repaid", "Loan fully repaid", tone="success")

        installments = session.exec(
            select(RepaymentSchedule).where(RepaymentSchedule.loan_id == loan.id).order_by(RepaymentSchedule.installment_number)
        ).all()
        for inst in installments:
            state = installment_state(inst, today)
            schedule.append(
                {
                    "installment_number": inst.installment_number,
                    "due_date": inst.due_date,
                    "amount_due": inst.amount_due,
                    "amount_paid": inst.amount_paid,
                    "principal_component": inst.principal_component,
                    "interest_component": inst.interest_component,
                    "state": state,
                    "days_past_due": max((today - inst.due_date).days, 0) if state == "overdue" else 0,
                }
            )
        split = balance_split(loan)
        open_items = [i for i in installments if not i.is_paid]
        next_due = min((i.due_date for i in open_items), default=None)
        loan_summary = {
            "loan_id": loan.id,
            "status": loan.status.value,
            "principal": loan.principal,
            "interest": loan.total_repayable - loan.principal,
            "penalties": loan.penalties_accrued,
            "total_owed": loan.total_repayable + loan.penalties_accrued,
            "repaid": split.repaid,
            "outstanding_balance": loan.outstanding_balance,
            "outstanding_principal": split.principal,
            "outstanding_interest": split.interest,
            "outstanding_penalties": split.penalties,
            "disbursed_at": loan.disbursed_at,
            "next_due_date": next_due,
            "days_past_due": max((today - next_due).days, 0) if next_due is not None else 0,
            "progress_pct": _pct(split.repaid, loan.total_repayable + loan.penalties_accrued),
        }

    events.sort(key=lambda e: e["at"])
    return {
        "application_id": application.id,
        "customer_full_name": customer.full_name if customer else "—",
        "customer_email": customer.email if customer else "",
        "customer_phone": profile.phone_number if profile else None,
        "customer_number": profile.customer_number if profile else None,
        "loan_product_name": product.name if product else "—",
        "branch_name": branch.name if branch else None,
        "amount_requested": application.amount_requested,
        "stage": application_stage(application, loan),
        "prepared_by_name": names.get(application.prepared_by) if application.prepared_by else None,
        "created_at": application.created_at,
        "loan": loan_summary,
        "events": events,
        "schedule": schedule,
    }
