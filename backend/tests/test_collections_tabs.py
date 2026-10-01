"""Collections "Due" and "Received" tabs, the customer-profile Loans
section, and the staff drill-down — all tenant-scoped by the central filter."""

from sqlmodel import Session, select

from app.models import User
from app.tenancy import tenant_context
from tests.test_disbursement_and_repayment import _auth_headers, _setup_approved_loan


def _disbursed_and_part_paid(client, engine, **kwargs):
    ctx = _setup_approved_loan(client, engine, **kwargs)
    loan_id = ctx["loan"]["id"]
    assert client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"])).status_code == 200
    resp = client.post(f"/loans/{loan_id}/repay", json={"amount": "1000.00"}, headers=_auth_headers(ctx["customer_token"]))
    assert resp.status_code == 200, resp.text
    return ctx


def test_received_lists_repayments_and_due_lists_upcoming_instalments(client, engine):
    ctx_a = _disbursed_and_part_paid(client, engine, company_name="Company A")
    ctx_b = _setup_approved_loan(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"])

    received = client.get("/credit/collections/received", headers=_auth_headers(ctx_a["admin_token"])).json()
    assert [(r["loan_id"], r["amount"]) for r in received] == [(ctx_a["loan"]["id"], "1000.00")]

    due = client.get("/credit/collections/due?days=90", headers=_auth_headers(ctx_a["admin_token"])).json()
    assert {d["loan_id"] for d in due} == {ctx_a["loan"]["id"]}
    assert all(d["amount_remaining"] != "0.00" for d in due)

    # Company B sees none of Company A's money.
    assert client.get("/credit/collections/received", headers=_auth_headers(ctx_b["admin_token"])).json() == []
    assert client.get("/credit/collections/due?days=90", headers=_auth_headers(ctx_b["admin_token"])).json() == []


def test_customer_profile_lists_their_loans(client, engine):
    ctx = _disbursed_and_part_paid(client, engine)
    with Session(engine) as session, tenant_context(ctx["company"]["id"]):
        customer_id = session.exec(select(User).where(User.email == "customer@companya.example.com")).one().id

    loans = client.get(f"/customers/{customer_id}/loans", headers=_auth_headers(ctx["admin_token"])).json()
    assert [(l["id"], l["status"]) for l in loans] == [(ctx["loan"]["id"], "active")]


def test_staff_detail_shows_handled_applications_and_activity(client, engine):
    ctx = _setup_approved_loan(client, engine)
    staff = client.get("/staff", headers=_auth_headers(ctx["admin_token"])).json()
    manager = next(s for s in staff if s["role"] == "branch_manager")

    resp = client.get(f"/staff/{manager['id']}", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["branch_name"] == "Main Branch"
    assert [a["involvement"] for a in body["applications"]] == ["decided"]
    assert body["recent_activity"]


def test_staff_detail_is_admin_only_and_tenant_scoped(client, engine):
    ctx_a = _setup_approved_loan(client, engine, company_name="Company A")
    ctx_b = _setup_approved_loan(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"])
    manager_a = next(s for s in client.get("/staff", headers=_auth_headers(ctx_a["admin_token"])).json() if s["role"] == "branch_manager")

    assert client.get(f"/staff/{manager_a['id']}", headers=_auth_headers(ctx_b["admin_token"])).status_code == 404
    assert client.get(f"/staff/{manager_a['id']}", headers=_auth_headers(ctx_a["manager_token"])).status_code == 403
