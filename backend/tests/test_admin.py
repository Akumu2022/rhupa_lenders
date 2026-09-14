"""CLAUDE.md §9/M8: system_administrator's company-wide oversight — KYC, applications,
loans, products, and the read-only portfolio aggregate. All company-scoped
(never cross-company) and restricted to system_administrator.
"""

import io
from decimal import Decimal

from sqlmodel import Session, select

from app.models import Loan, User
from app.tenancy import tenant_context
from tests.conftest import create_branch, seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_disbursed_loan(client, engine, *, company_name="Company A", platform_token=None, amount="5000.00"):
    if platform_token is None:
        seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
        platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")

    slug = company_name.lower().replace(" ", "")
    company = client.post(
        "/platform/companies",
        json={
            "name": company_name,
            "admin_email": f"admin@{slug}.example.com",
            "admin_password": "admin-pass-123",
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    ).json()
    admin_token = _login(client, f"admin@{slug}.example.com", "admin-pass-123")
    branch = create_branch(client, admin_token, code=f"{slug.upper()}-1")

    client.post(
        "/staff",
        json={
            "email": f"compliance@{slug}.example.com",
            "password": "compliance-pass-1",
            "full_name": "Compliance One",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    )
    compliance_token = _login(client, f"compliance@{slug}.example.com", "compliance-pass-1")
    # Kept as one credit_officer (not two, as before M13) — fewer logins
    # keeps this file's two-company tests under the /auth/login rate limit.
    credit_token = compliance_token

    client.post(
        "/staff",
        json={
            "email": f"manager@{slug}.example.com",
            "password": "manager-pass-123",
            "full_name": "Manager One",
            "role": "branch_manager",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    )
    manager_token = _login(client, f"manager@{slug}.example.com", "manager-pass-123")

    client.post(
        "/staff",
        json={
            "email": f"finance@{slug}.example.com",
            "password": "finance-pass-123",
            "full_name": "Finance One",
            "role": "cashier_finance_officer",
        },
        headers=_auth_headers(admin_token),
    )
    finance_token = _login(client, f"finance@{slug}.example.com", "finance-pass-123")

    signup_resp = client.post(
        "/signup",
        json={"signup_code": company["signup_code"], "email": f"customer@{slug}.example.com", "password": "customer-pass-1", "full_name": "Customer One"},
    )
    customer_token = signup_resp.json()["access_token"]

    # CLAUDE.md §7: self-signup never sets branch_id — patched directly here
    # so this application routes to branch review, same shortcut as
    # tests/test_credit.py (this suite is about admin oversight, not
    # registration mechanics).
    with Session(engine) as session:
        with tenant_context(company["id"]):
            customer = session.exec(select(User).where(User.email == f"customer@{slug}.example.com")).first()
            customer.branch_id = branch["id"]
            session.add(customer)
            session.commit()

    client.post(
        "/profile",
        headers=_auth_headers(customer_token),
        data={
            "date_of_birth": "1995-05-05",
            "national_id_number": f"NATID-{slug}",
            "phone_number": "+254700000000",
            "residential_address": "123 Main St",
            "employment_status": "employed",
            "monthly_income": "45000.00",
            "occupation": "Engineer",
        },
        files={
            "id_document": ("id-front.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg"),
            "id_document_back": ("id-back.jpg", io.BytesIO(b"fake-image-bytes-back"), "image/jpeg"),
        },
    )
    queue = client.get("/compliance/queue", headers=_auth_headers(compliance_token)).json()
    profile_id = queue[0]["id"]
    client.post(f"/compliance/profiles/{profile_id}/verify", json={"notes": None}, headers=_auth_headers(compliance_token))

    products = client.get("/loan-products", headers=_auth_headers(customer_token)).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")
    application = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": amount},
        headers=_auth_headers(customer_token),
    ).json()
    approval = client.post(
        f"/branch-manager/applications/{application['id']}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(manager_token),
    ).json()
    with Session(engine) as session:
        with tenant_context(company["id"]):
            loan_id = session.exec(select(Loan).where(Loan.application_id == application["id"])).first().id
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(finance_token))

    return {
        "platform_token": platform_token,
        "admin_token": admin_token,
        "compliance_token": compliance_token,
        "credit_token": credit_token,
        "manager_token": manager_token,
        "finance_token": finance_token,
        "customer_token": customer_token,
        "company": company,
        "loan_id": loan_id,
        "product_id": salary_advance["id"],
    }


def test_admin_sees_all_kyc_profiles_regardless_of_status(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.get("/admin/kyc", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["kyc_status"] == "verified"


def test_admin_sees_all_applications_regardless_of_status(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.get("/admin/applications", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "approved"


def test_admin_sees_all_loans(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.get("/admin/loans", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    loan = resp.json()[0]
    assert loan["status"] == "active"
    assert loan["customer_full_name"] == "Customer One"
    assert loan["principal"] == "5000.00"


def test_admin_oversight_is_tenant_isolated(client, engine):
    ctx_a = _setup_disbursed_loan(client, engine, company_name="Company A")
    ctx_b = _setup_disbursed_loan(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"])

    for endpoint in ("/admin/kyc", "/admin/applications", "/admin/loans"):
        resp = client.get(endpoint, headers=_auth_headers(ctx_a["admin_token"]))
        assert len(resp.json()) == 1, endpoint

    assert ctx_a["loan_id"] != ctx_b["loan_id"]


def test_non_admin_cannot_access_oversight_endpoints(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    for endpoint in (
        "/admin/kyc",
        "/admin/applications",
        "/admin/loans",
        "/admin/products",
        "/admin/portfolio/summary",
        "/admin/portfolio/trend",
    ):
        resp = client.get(endpoint, headers=_auth_headers(ctx["credit_token"]))
        assert resp.status_code == 403, endpoint


def test_admin_lists_all_products_including_inactive(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.get("/admin/products", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert names == {"Salary Advance", "Emergency Loan", "Business Loan"}


def test_admin_can_update_product_and_it_writes_audit(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.patch(
        f"/admin/products/{ctx['product_id']}",
        json={"interest_rate": "6.50", "is_active": False},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["interest_rate"] == "6.50"
    assert resp.json()["is_active"] is False

    # Deactivated products no longer show up for customers.
    products = client.get("/loan-products", headers=_auth_headers(ctx["customer_token"])).json()
    assert not any(p["id"] == ctx["product_id"] for p in products)

    audit = client.get("/admin/audit-log", headers=_auth_headers(ctx["admin_token"])).json()
    assert any(entry["action"] == "loan_product.update" for entry in audit)


def test_admin_can_update_product_name_description_and_term(client, engine):
    """CLAUDE.md §19: products are data rows a system_administrator edits — every
    product-defining field, not just amounts/rate/active status."""
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.patch(
        f"/admin/products/{ctx['product_id']}",
        json={
            "name": "Payday Advance",
            "description": "Renamed and re-termed product",
            "repayment_period_days": 45,
        },
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Payday Advance"
    assert body["description"] == "Renamed and re-termed product"
    assert body["repayment_period_days"] == 45


def test_admin_cannot_set_min_amount_above_max_amount(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.patch(
        f"/admin/products/{ctx['product_id']}",
        json={"min_amount": "999999.00"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 400


def test_portfolio_summary_reflects_disbursed_and_active_loan(client, engine):
    ctx = _setup_disbursed_loan(client, engine, amount="5000.00")
    resp = client.get("/admin/portfolio/summary", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_disbursed"] == "5000.00"
    assert body["active_loans"] == 1
    assert body["active_borrowers"] == 1
    # CLAUDE.md §29: outstanding_principal is PRINCIPAL only (not the
    # interest-inclusive total_repayable/outstanding_balance) — nothing's
    # been repaid yet, so it equals the full principal, 5000.00, not 5250.00.
    assert Decimal(body["outstanding_principal"]) == Decimal("5000.00")
    assert body["par_percentage"] == "0.00"


def test_portfolio_summary_is_tenant_isolated(client, engine):
    ctx_a = _setup_disbursed_loan(client, engine, company_name="Company A", amount="5000.00")
    _setup_disbursed_loan(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"], amount="20000.00")

    resp = client.get("/admin/portfolio/summary", headers=_auth_headers(ctx_a["admin_token"]))
    assert resp.json()["total_disbursed"] == "5000.00"


def test_portfolio_trend_reflects_todays_disbursement(client, engine):
    ctx = _setup_disbursed_loan(client, engine, amount="5000.00")
    resp = client.get("/admin/portfolio/trend", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 200, resp.text
    points = resp.json()["points"]
    assert len(points) == 14
    today_point = points[-1]
    assert today_point["disbursed_count"] == 1
    assert today_point["disbursed_amount"] == "5000.00"
    assert all(p["disbursed_count"] == 0 for p in points[:-1])


def test_portfolio_trend_is_tenant_isolated(client, engine):
    ctx_a = _setup_disbursed_loan(client, engine, company_name="Company A", amount="5000.00")
    _setup_disbursed_loan(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"], amount="20000.00")

    resp = client.get("/admin/portfolio/trend", headers=_auth_headers(ctx_a["admin_token"]))
    today_point = resp.json()["points"][-1]
    assert today_point["disbursed_amount"] == "5000.00"
