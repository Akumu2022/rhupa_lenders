"""Shared staff analytics (app/routers/analytics.py): dashboard totals,
all-stages applications list, per-application movement timeline, and the
prepared_by stamp that drives each officer's "mine" views."""

from datetime import date, timedelta

from sqlmodel import Session, select

from app.time_utils import business_today
from app.models import LoanApplication, RepaymentSchedule
from app.tenancy import tenant_context
from tests.test_credit import _auth_headers, _login, _setup_company_with_branch_review_application
from tests.test_finance import _approve_and_disburse


def _stage(items, stage):
    return next(s for s in items if s["stage"] == stage)


def test_self_service_application_has_no_preparer(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            application = session.get(LoanApplication, ctx["application"]["id"])
            assert application.prepared_by is None


def test_officer_assisted_application_is_stamped_with_preparer(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    reject = client.post(
        f"/branch-manager/applications/{ctx['application']['id']}/decide",
        json={"decision": "reject", "comments": "Resubmit via officer"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert reject.status_code == 200, reject.text

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            customer_id = session.get(LoanApplication, ctx["application"]["id"]).customer_id

    resp = client.post(
        f"/customers/{customer_id}/applications",
        json={"loan_product_id": ctx["loan_product"]["id"], "amount_requested": "4000.00"},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert resp.status_code == 201, resp.text

    mine = client.get("/analytics/applications?mine=true", headers=_auth_headers(ctx["credit_token"])).json()
    assert [a["id"] for a in mine] == [resp.json()["id"]]
    assert mine[0]["prepared_by_name"] == "Credit One"

    # Without mine=true the officer sees their whole branch, rejected one included.
    branch = client.get("/analytics/applications", headers=_auth_headers(ctx["credit_token"])).json()
    assert {a["stage"] for a in branch} == {"in_review", "rejected"}


def test_credit_officer_still_sees_application_after_approval_and_disbursement(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _approve_and_disburse(client, engine, ctx)

    items = client.get("/analytics/applications", headers=_auth_headers(ctx["credit_token"])).json()
    assert len(items) == 1
    assert items[0]["stage"] == "active"
    assert items[0]["principal"] == "5000.00"
    assert items[0]["next_due_date"] is not None


def test_dashboard_totals_after_disbursement_and_repayment(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)
    client.post(f"/loans/{loan_id}/repay", json={"amount": "2000.00"}, headers=_auth_headers(ctx["customer_token"]))

    body = client.get("/analytics/dashboard", headers=_auth_headers(ctx["finance_token"])).json()
    assert body["scope"] == "company"
    assert body["flows"]["disbursed_amount"] == "5000.00"
    assert body["flows"]["disbursed_count"] == 1
    assert body["flows"]["collected_amount"] == "2000.00"
    assert body["queues"]["in_review_count"] == 0
    assert body["queues"]["awaiting_disbursement_count"] == 0
    assert _stage(body["pipeline"], "active")["count"] == 1
    portfolio = body["portfolio"]
    assert portfolio["active_loans"] == 1
    assert portfolio["total_repaid_all_time"] == "2000.00"
    # Interest before principal: of the 2000 paid, 250 clears the 5% interest
    # and 1750 goes to principal, leaving 3250 of the 5000 principal.
    assert portfolio["outstanding_principal"] == "3250.00"
    assert portfolio["outstanding_interest"] == "0.00"
    assert portfolio["par_pct"] == "0.00"
    assert {a["bucket"]: a["count"] for a in body["aging"]}["current"] == 1

    # The credit officer's view of the same book is branch-scoped.
    officer = client.get("/analytics/dashboard", headers=_auth_headers(ctx["credit_token"])).json()
    assert officer["scope"] == "branch"
    assert officer["flows"]["disbursed_amount"] == "5000.00"


def test_overdue_installment_lands_in_aging_and_due_list(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            inst = session.exec(select(RepaymentSchedule).where(RepaymentSchedule.loan_id == loan_id)).first()
            inst.due_date = business_today() - timedelta(days=10)
            session.add(inst)
            session.commit()

    body = client.get("/analytics/dashboard", headers=_auth_headers(ctx["credit_token"])).json()
    aging = {a["bucket"]: a for a in body["aging"]}
    assert aging["8-30"]["count"] == 1
    assert body["portfolio"]["overdue_loans"] == 1
    assert body["portfolio"]["par_pct"] == "100.00"
    assert body["due"]["overdue_installments"] == 1
    assert body["due_list"][0]["state"] == "overdue"
    assert body["due_list"][0]["days_past_due"] == 10
    assert body["due_list"][0]["customer_full_name"] == "Customer One"


def test_timeline_records_each_movement(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)
    client.post(f"/loans/{loan_id}/repay", json={"amount": "1000.00"}, headers=_auth_headers(ctx["customer_token"]))

    resp = client.get(
        f"/analytics/applications/{ctx['application']['id']}/timeline", headers=_auth_headers(ctx["credit_token"])
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    kinds = [e["kind"] for e in body["events"]]
    for expected in ("kyc", "submitted", "review", "loan_created", "disbursed", "repayment"):
        assert expected in kinds, kinds
    review = next(e for e in body["events"] if e["kind"] == "review")
    assert review["actor_name"] == "Manager One"
    disbursed = next(e for e in body["events"] if e["kind"] == "disbursed")
    assert disbursed["actor_name"] == "Finance One"
    assert body["loan"]["repaid"] == "1000.00"
    assert len(body["schedule"]) >= 1
    assert body["stage"] == "active"


def test_management_gets_aggregates_only(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _approve_and_disburse(client, engine, ctx)
    resp = client.post(
        "/staff",
        json={"email": "mgmt@companya.example.com", "password": "mgmt-pass-123", "full_name": "Mgmt", "role": "management"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 201, resp.text
    token = _login(client, "mgmt@companya.example.com", "mgmt-pass-123")

    body = client.get("/analytics/dashboard", headers=_auth_headers(token)).json()
    assert body["flows"]["disbursed_amount"] == "5000.00"
    assert body["due_list"] == []
    assert client.get("/analytics/applications", headers=_auth_headers(token)).status_code == 403
    assert (
        client.get(f"/analytics/applications/{ctx['application']['id']}/timeline", headers=_auth_headers(token)).status_code
        == 403
    )


def test_customer_cannot_access_analytics(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    assert client.get("/analytics/dashboard", headers=_auth_headers(ctx["customer_token"])).status_code == 403


def test_inverted_date_range_is_rejected(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    resp = client.get(
        "/analytics/dashboard?start=2026-09-10&end=2026-09-01", headers=_auth_headers(ctx["finance_token"])
    )
    assert resp.status_code == 400


def test_analytics_never_crosses_companies(client, engine):
    """CLAUDE.md §5/rule #12: Company B's book must not appear anywhere in
    Company A's analytics, and B's timeline must be unreachable from A."""
    a = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    b = _setup_company_with_branch_review_application(
        client, engine, company_name="Company B", platform_token=a["platform_token"], include_finance=True,
        amount_requested="7000.00",
    )
    _approve_and_disburse(client, engine, b)

    body = client.get("/analytics/dashboard", headers=_auth_headers(a["finance_token"])).json()
    assert body["flows"]["disbursed_amount"] == "0.00"
    assert body["portfolio"]["total_disbursed_all_time"] == "0.00"
    assert body["queues"]["in_review_count"] == 1  # A's own pending application only

    items = client.get("/analytics/applications", headers=_auth_headers(a["finance_token"])).json()
    assert [i["id"] for i in items] == [a["application"]["id"]]

    resp = client.get(
        f"/analytics/applications/{b['application']['id']}/timeline", headers=_auth_headers(a["finance_token"])
    )
    assert resp.status_code == 404


def test_officer_without_branch_sees_only_unassigned_applications(client, engine):
    """Legacy accounts predating M10 have no branch. They must see the
    equally-unassigned applications in their own company, never be widened
    to the whole company (and never see branch-assigned ones)."""
    from app.models import User

    ctx = _setup_company_with_branch_review_application(client, engine)
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            officer = session.exec(select(User).where(User.email == "credit@companya.example.com")).first()
            officer.branch_id = None
            session.add(officer)
            session.commit()

    body = client.get("/analytics/dashboard", headers=_auth_headers(ctx["credit_token"])).json()
    assert body["scope"] == "unassigned"
    # The only application is branch-assigned, so it is out of scope.
    assert body["queues"]["in_review_count"] == 0
    assert client.get("/analytics/applications", headers=_auth_headers(ctx["credit_token"])).json() == []
    resp = client.get(
        f"/analytics/applications/{ctx['application']['id']}/timeline", headers=_auth_headers(ctx["credit_token"])
    )
    assert resp.status_code == 404

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            application = session.get(LoanApplication, ctx["application"]["id"])
            application.branch_id = None
            session.add(application)
            session.commit()

    items = client.get("/analytics/applications", headers=_auth_headers(ctx["credit_token"])).json()
    assert [i["id"] for i in items] == [ctx["application"]["id"]]


def test_branch_manager_sees_branch_dashboard_list_and_timeline(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _approve_and_disburse(client, engine, ctx)
    headers = _auth_headers(ctx["manager_token"])

    body = client.get("/analytics/dashboard", headers=headers).json()
    assert body["scope"] == "branch"
    assert body["flows"]["disbursed_amount"] == "5000.00"
    assert body["due_list"] == [] or body["due_list"][0]["customer_full_name"] == "Customer One"

    items = client.get("/analytics/applications", headers=headers).json()
    assert [i["stage"] for i in items] == ["active"]
    resp = client.get(f"/analytics/applications/{ctx['application']['id']}/timeline", headers=headers)
    assert resp.status_code == 200
