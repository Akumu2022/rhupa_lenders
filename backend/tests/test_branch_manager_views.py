"""CLAUDE.md §9/§25: branch manager's read-only visibility into their own
branch's staff, portfolio, and collections — ordinary hand-filtered
branch_id queries (§5's asymmetry), covered separately from the
approval-chain tests in tests/test_credit.py.
"""

from datetime import date, timedelta

from sqlmodel import Session, select

from app.models import Loan, RepaymentSchedule
from app.tenancy import tenant_context
from tests.test_credit import (
    _auth_headers,
    _setup_company_with_branch_review_application,
)


def test_branch_manager_staff_lists_only_own_branch(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    resp = client.get("/branch-manager/staff", headers=_auth_headers(ctx["manager_token"]))
    assert resp.status_code == 200
    names = {s["full_name"] for s in resp.json()}
    # The manager sees themselves and the credit officer, both in this branch.
    assert "Credit One" in names
    assert "Manager One" in names


def test_branch_manager_portfolio_reflects_own_branch_only(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    application_id = ctx["application"]["id"]

    client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loan_id = session.exec(select(Loan)).first().id
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))

    resp = client.get("/branch-manager/portfolio", headers=_auth_headers(ctx["manager_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_disbursed"] == "5000.00"
    assert body["active_loans"] == 1
    assert body["outstanding_principal"] == "5000.00"


def test_branch_manager_portfolio_excludes_other_branches(client, engine):
    ctx_a = _setup_company_with_branch_review_application(client, engine, company_name="Company A")
    ctx_b = _setup_company_with_branch_review_application(
        client, engine, company_name="Company B", platform_token=ctx_a["platform_token"]
    )
    # Company A's manager approves nothing — their portfolio must stay at zero,
    # unaffected by Company B's own (separate-company, separately tenant-
    # scoped) application.
    resp = client.get("/branch-manager/portfolio", headers=_auth_headers(ctx_a["manager_token"]))
    assert resp.status_code == 200
    assert resp.json()["active_loans"] == 0
    assert ctx_b["application"]["id"] != ctx_a["application"]["id"]


def test_branch_manager_collections_lists_own_branch_overdue_loans(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    application_id = ctx["application"]["id"]

    client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loan = session.exec(select(Loan)).first()
            loan_id = loan.id
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            schedule = session.exec(select(RepaymentSchedule).where(RepaymentSchedule.loan_id == loan_id)).first()
            schedule.due_date = date.today() - timedelta(days=2)
            session.add(schedule)
            session.commit()

    resp = client.get("/branch-manager/collections", headers=_auth_headers(ctx["manager_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == loan_id
    assert body[0]["days_overdue"] == 2


def test_non_branch_manager_cannot_access_branch_views(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    for endpoint in ("/branch-manager/staff", "/branch-manager/portfolio", "/branch-manager/collections"):
        resp = client.get(endpoint, headers=_auth_headers(ctx["credit_token"]))
        assert resp.status_code == 403, endpoint
