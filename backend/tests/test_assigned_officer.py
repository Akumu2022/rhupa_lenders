"""Customer ownership: assigned credit officer, reassignment rules, and the
"mine" views that count it."""

from sqlmodel import Session, select

from app.models import AuditLog, User
from app.tenancy import tenant_context
from tests.conftest import create_branch
from tests.test_credit import _auth_headers, _login, _setup_company_with_branch_review_application


def _customer_id(engine, ctx):
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            return session.exec(select(User).where(User.email == "customer@companya.example.com")).one().id


def _add_officer(client, ctx, email, branch_id):
    resp = client.post(
        "/staff",
        json={"email": email, "password": "credit-pass-123", "full_name": email.split("@")[0], "role": "credit_officer", "branch_id": branch_id},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"], _login(client, email, "credit-pass-123")


def _assign(client, token, customer_id, officer_id):
    return client.patch(f"/customers/{customer_id}/officer", json={"officer_id": officer_id}, headers=_auth_headers(token))


def test_branch_manager_assigns_officer_and_it_is_audited(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    customer = _customer_id(engine, ctx)
    officer_id, _ = _add_officer(client, ctx, "second@companya.example.com", ctx["branch"]["id"])

    resp = _assign(client, ctx["manager_token"], customer, officer_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["assigned_officer_name"] == "second"
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            assert session.exec(select(AuditLog).where(AuditLog.action == "customer.officer_assign")).one().entity_id == customer


def test_officer_must_be_active_credit_officer_in_customers_branch(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    customer = _customer_id(engine, ctx)
    other_branch = create_branch(client, ctx["admin_token"], name="Other", code="OTHER")
    far_officer, _ = _add_officer(client, ctx, "far@companya.example.com", other_branch["id"])
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            manager_id = session.exec(select(User).where(User.email == "manager@companya.example.com")).one().id

    assert _assign(client, ctx["admin_token"], customer, far_officer).status_code == 400  # wrong branch
    assert _assign(client, ctx["admin_token"], customer, manager_id).status_code == 400  # not a credit officer


def test_branch_manager_cannot_reassign_outside_own_branch(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    customer = _customer_id(engine, ctx)
    other_branch = create_branch(client, ctx["admin_token"], name="Other", code="OTHER")
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            user = session.get(User, customer)
            user.branch_id = other_branch["id"]
            session.add(user)
            session.commit()
    officer_id, _ = _add_officer(client, ctx, "o2@companya.example.com", other_branch["id"])
    assert _assign(client, ctx["manager_token"], customer, officer_id).status_code == 404
    assert _assign(client, ctx["admin_token"], customer, officer_id).status_code == 200


def test_only_manager_and_admin_can_reassign(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    customer = _customer_id(engine, ctx)
    officer_id, officer_token = _add_officer(client, ctx, "o3@companya.example.com", ctx["branch"]["id"])
    assert _assign(client, officer_token, customer, officer_id).status_code == 403
    assert _assign(client, ctx["customer_token"], customer, officer_id).status_code == 403


def test_mine_views_include_assigned_customers_self_service_applications(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    customer = _customer_id(engine, ctx)
    officer_id, officer_token = _add_officer(client, ctx, "owner@companya.example.com", ctx["branch"]["id"])

    # Self-service application, nobody owns the customer yet: not "mine".
    assert client.get("/analytics/applications?mine=true", headers=_auth_headers(officer_token)).json() == []
    assert client.get("/customers?mine=true", headers=_auth_headers(officer_token)).json() == []

    _assign(client, ctx["manager_token"], customer, officer_id)
    mine = client.get("/analytics/applications?mine=true", headers=_auth_headers(officer_token)).json()
    assert [a["id"] for a in mine] == [ctx["application"]["id"]]
    assert [c["id"] for c in client.get("/customers?mine=true", headers=_auth_headers(officer_token)).json()] == [customer]
    # The other officer in the same branch still sees it branch-wide, but not as theirs.
    assert client.get("/analytics/applications?mine=true", headers=_auth_headers(ctx["credit_token"])).json() == []


def test_moving_customer_to_another_branch_clears_old_branch_officer(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    customer = _customer_id(engine, ctx)
    officer_id, _ = _add_officer(client, ctx, "owner@companya.example.com", ctx["branch"]["id"])
    _assign(client, ctx["manager_token"], customer, officer_id)
    other_branch = create_branch(client, ctx["admin_token"], name="Other", code="OTHER")

    resp = client.patch(f"/admin/users/{customer}/branch", json={"branch_id": other_branch["id"]}, headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 200, resp.text
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            assert session.get(User, customer).assigned_officer_id is None


def test_cannot_reassign_another_companys_customer(client, engine):
    a = _setup_company_with_branch_review_application(client, engine)
    b = _setup_company_with_branch_review_application(client, engine, company_name="Company B", platform_token=a["platform_token"])
    with Session(engine) as session:
        with tenant_context(b["company"]["id"]):
            b_customer = session.exec(select(User).where(User.email == "customer@companyb.example.com")).one().id
    officer_id, _ = _add_officer(client, a, "o@companya.example.com", a["branch"]["id"])
    assert _assign(client, a["admin_token"], b_customer, officer_id).status_code == 404
