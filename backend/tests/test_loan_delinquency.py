"""CLAUDE.md §19: collections/delinquency stage (active -> overdue ->
defaulted) and the amortization breakdown on each repayment installment.
active -> overdue is system-computed (app/loan_delinquency.py); overdue ->
defaulted is always an explicit, reasoned staff action.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlmodel import Session, select

from app.models import AuditLog, RepaymentSchedule
from app.tenancy import tenant_context
from tests.test_disbursement_and_repayment import _auth_headers, _setup_approved_loan


def _backdate_schedule(engine, company_id, loan_id, days_ago=5):
    """Simulates time passing: pushes the loan's single installment due_date
    into the past so it reads as overdue without needing to wait for real time."""
    with Session(engine) as session:
        with tenant_context(company_id):
            schedule = session.exec(select(RepaymentSchedule).where(RepaymentSchedule.loan_id == loan_id)).first()
            schedule.due_date = date.today() - timedelta(days=days_ago)
            session.add(schedule)
            session.commit()


def test_amortization_breakdown_sums_to_amount_due(client, engine):
    """CLAUDE.md §19 borrower transparency: principal + interest == amount due."""
    ctx = _setup_approved_loan(client, engine, amount="5000.00")
    loan_id = ctx["loan"]["id"]
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))

    loans_me = client.get("/loans/me", headers=_auth_headers(ctx["customer_token"])).json()
    installment = loans_me["loans"][0]["schedule"][0]
    assert installment["principal_component"] == "5000.00"
    assert installment["interest_component"] == "250.00"  # 5% of 5000
    assert Decimal(installment["principal_component"]) + Decimal(installment["interest_component"]) == Decimal(
        installment["amount_due"]
    )


def test_loan_becomes_overdue_after_due_date_passes(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    _backdate_schedule(engine, ctx["company"]["id"], loan_id)

    loans_me = client.get("/loans/me", headers=_auth_headers(ctx["customer_token"])).json()
    assert loans_me["loans"][0]["status"] == "overdue"
    # Still counts against the customer's available credit (CLAUDE.md §19).
    # 5 days overdue, 3-day grace (CLAUDE.md §23 DEV placeholder) => 3 days of
    # 1%/day penalty, compounding on the owed amount:
    #   5250.00 -> +52.50 -> 5302.50 -> +53.03 -> 5355.53 -> +53.56 -> 5409.09
    # loan_limit (200000, the Business product's max) minus that 5409.09.
    assert loans_me["loans"][0]["penalties_accrued"] == "159.09"
    assert loans_me["loans"][0]["outstanding_balance"] == "5409.09"
    assert loans_me["available_credit"] == "194590.91"


def test_collections_queue_lists_overdue_loans_and_is_tenant_scoped(client, engine):
    ctx_a = _setup_approved_loan(client, engine, company_name="Company A")
    loan_a = ctx_a["loan"]["id"]
    client.post(f"/finance/loans/{loan_a}/disburse", headers=_auth_headers(ctx_a["finance_token"]))
    _backdate_schedule(engine, ctx_a["company"]["id"], loan_a, days_ago=3)

    ctx_b = _setup_approved_loan(
        client, engine, company_name="Company B", platform_token=ctx_a["platform_token"]
    )
    loan_b = ctx_b["loan"]["id"]
    client.post(f"/finance/loans/{loan_b}/disburse", headers=_auth_headers(ctx_b["finance_token"]))
    # Company B's loan is disbursed but not yet overdue.

    queue_a = client.get("/credit/loans/collections", headers=_auth_headers(ctx_a["credit_token"])).json()
    assert len(queue_a) == 1
    assert queue_a[0]["id"] == loan_a
    assert queue_a[0]["days_overdue"] == 3

    # Company B's credit officer sees neither their own (not overdue) nor
    # company A's overdue loan — the central tenant filter, not hand-rolled.
    queue_b = client.get("/credit/loans/collections", headers=_auth_headers(ctx_b["credit_token"])).json()
    assert queue_b == []


def test_mark_loan_defaulted_requires_overdue_status(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))

    # Not overdue yet — defaulting should be rejected.
    resp = client.post(
        f"/credit/loans/{loan_id}/mark-defaulted",
        json={"reason": "Too early"},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert resp.status_code == 409

    _backdate_schedule(engine, ctx["company"]["id"], loan_id)
    client.get("/credit/loans/collections", headers=_auth_headers(ctx["credit_token"]))  # triggers the sync

    resp = client.post(
        f"/credit/loans/{loan_id}/mark-defaulted",
        json={"reason": "No response after repeated follow-up"},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "defaulted"

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            audits = session.exec(select(AuditLog).where(AuditLog.action == "loan.mark_defaulted")).all()
    assert len(audits) == 1
    assert audits[0].entity_id == loan_id
    assert audits[0].reason == "No response after repeated follow-up"


def test_mark_loan_defaulted_requires_a_reason(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    _backdate_schedule(engine, ctx["company"]["id"], loan_id)
    client.get("/credit/loans/collections", headers=_auth_headers(ctx["credit_token"]))

    resp = client.post(
        f"/credit/loans/{loan_id}/mark-defaulted",
        json={"reason": ""},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert resp.status_code == 422


def test_repayment_allowed_on_overdue_and_defaulted_loans(client, engine):
    """CLAUDE.md §6/rule #10: repayment stays open even once delinquent —
    never trap a borrower who's trying to catch up."""
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    _backdate_schedule(engine, ctx["company"]["id"], loan_id)
    client.get("/credit/loans/collections", headers=_auth_headers(ctx["credit_token"]))
    client.post(
        f"/credit/loans/{loan_id}/mark-defaulted",
        json={"reason": "No response"},
        headers=_auth_headers(ctx["credit_token"]),
    )

    # CLAUDE.md §23: 5 days overdue, 3-day grace => 3 penalty days accrued
    # (see test_loan_becomes_overdue_after_due_date_passes for the exact
    # compounding), so the full amount owed is now 5409.09, not just 5250.00.
    resp = client.post(
        f"/loans/{loan_id}/repay",
        json={"amount": "5409.09"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "repaid"


def test_admin_portfolio_summary_reports_overdue_and_defaulted_counts(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    _backdate_schedule(engine, ctx["company"]["id"], loan_id)

    summary = client.get("/admin/portfolio/summary", headers=_auth_headers(ctx["admin_token"])).json()
    assert summary["overdue_loans"] == 1
    assert summary["defaulted_loans"] == 0
    assert Decimal(summary["par_percentage"]) == Decimal("100.00")
