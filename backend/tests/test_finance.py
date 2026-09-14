"""CLAUDE.md §28/§30 (M14/M17): cashier/finance officer — disbursement role
gate is covered in tests/test_disbursement_and_repayment.py; this file
covers the expense ledger and the derived financial views.
"""

from datetime import date, timedelta

from sqlmodel import Session, select

from app.models import Loan
from app.tenancy import tenant_context
from tests.test_credit import _auth_headers, _setup_company_with_branch_review_application


def _approve_and_disburse(client, engine, ctx):
    application_id = ctx["application"]["id"]
    client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loan_id = session.exec(select(Loan)).first().id
    disburse = client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert disburse.status_code == 200, disburse.text
    return loan_id


def test_create_expense_writes_audit_and_appears_in_financials(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)

    resp = client.post(
        "/finance/expenses",
        json={"category": "rent", "amount": "1500.00", "description": "Branch rent"},
        headers=_auth_headers(ctx["finance_token"]),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["category"] == "rent"
    assert body["amount"] == "1500.00"
    assert body["created_by_name"] == "Finance One"

    financials = client.get("/finance/financials", headers=_auth_headers(ctx["finance_token"])).json()
    assert financials["total_expenses"] == "1500.00"
    assert len(financials["recent_expenses"]) == 1
    assert financials["recent_expenses"][0]["description"] == "Branch rent"


def test_financials_reflects_disbursement_and_repayment_income(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)

    client.post(
        f"/loans/{loan_id}/repay",
        json={"amount": "2000.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )

    financials = client.get("/finance/financials", headers=_auth_headers(ctx["finance_token"])).json()
    assert financials["total_disbursed"] == "5000.00"
    assert financials["total_repayment_income"] == "2000.00"
    # No penalties or expenses in this test — net income is just the repayment.
    assert financials["net"] == "2000.00"


def test_reports_endpoint_is_parameterized_by_date_range(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _approve_and_disburse(client, engine, ctx)

    today = date.today()
    resp = client.get(
        "/finance/reports",
        params={"start_date": (today - timedelta(days=1)).isoformat(), "end_date": today.isoformat()},
        headers=_auth_headers(ctx["finance_token"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_disbursed"] == "5000.00"
    assert body["active_loans"] == 1

    # A window that excludes today sees none of it.
    old_window = client.get(
        "/finance/reports",
        params={
            "start_date": (today - timedelta(days=30)).isoformat(),
            "end_date": (today - timedelta(days=10)).isoformat(),
        },
        headers=_auth_headers(ctx["finance_token"]),
    )
    assert old_window.json()["total_disbursed"] == "0.00"


def test_reports_rejects_inverted_date_range(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    today = date.today()
    resp = client.get(
        "/finance/reports",
        params={"start_date": today.isoformat(), "end_date": (today - timedelta(days=1)).isoformat()},
        headers=_auth_headers(ctx["finance_token"]),
    )
    assert resp.status_code == 400


def test_non_finance_officer_cannot_access_finance_endpoints(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    for endpoint in ("/finance/disbursements", "/finance/financials"):
        resp = client.get(endpoint, headers=_auth_headers(ctx["manager_token"]))
        assert resp.status_code == 403, endpoint

    resp = client.post(
        "/finance/expenses",
        json={"category": "rent", "amount": "100.00"},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert resp.status_code == 403
