"""Sidebar alert counts (GET /nav-badges): each role sees only the work
waiting on them, keyed by nav path, and nothing when the queue is empty."""

from sqlmodel import Session, select

from app.models import Loan
from app.tenancy import tenant_context
from tests.test_credit import _auth_headers, _setup_company_with_branch_review_application


def _badges(client, token):
    resp = client.get("/nav-badges", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_branch_manager_sees_pending_application_then_finance_sees_disbursement(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)

    # Submitted application is waiting on the branch manager, not on finance.
    assert _badges(client, ctx["manager_token"]) == {"/branch-manager/applications": 1}
    assert _badges(client, ctx["finance_token"]) == {}

    client.post(
        f"/branch-manager/applications/{ctx['application']['id']}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(ctx["manager_token"]),
    )

    # Approved: manager's queue clears, the loan now waits for finance.
    assert _badges(client, ctx["manager_token"]) == {}
    assert _badges(client, ctx["finance_token"]) == {"/finance/disbursements": 1}

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loan_id = session.exec(select(Loan)).first().id
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert _badges(client, ctx["finance_token"]) == {}


def test_nav_badges_requires_login(client):
    assert client.get("/nav-badges").status_code == 401
