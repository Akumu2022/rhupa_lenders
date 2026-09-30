"""CLAUDE.md §9/M8: system_administrator's company-wide oversight — KYC, applications,
loans, products, and the read-only portfolio aggregate. All company-scoped
(never cross-company) and restricted to system_administrator.
"""

import io
from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from app.loan_calculation import generate_schedule
from app.models import InterestModel, Loan, User
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


# The admin portfolio figures now come from the shared analytics endpoint
# (/admin/portfolio/* was removed so every screen reads one source).


def test_admin_dashboard_reflects_disbursed_and_active_loan(client, engine):
    ctx = _setup_disbursed_loan(client, engine, amount="5000.00")
    resp = client.get("/analytics/dashboard", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "company"
    assert body["portfolio"]["total_disbursed_all_time"] == "5000.00"
    assert body["portfolio"]["active_loans"] == 1
    assert body["portfolio"]["active_borrowers"] == 1
    # CLAUDE.md §29: outstanding principal is PRINCIPAL only: nothing repaid
    # yet, so the full 5000.00, not the interest-inclusive 5250.00.
    assert Decimal(body["portfolio"]["outstanding_principal"]) == Decimal("5000.00")
    assert body["portfolio"]["par_pct"] == "0.00"
    # Today's disbursement shows in the time series.
    assert sum(Decimal(p["disbursed"]) for p in body["series"]) == Decimal("5000.00")


def test_admin_dashboard_is_tenant_isolated(client, engine):
    ctx_a = _setup_disbursed_loan(client, engine, company_name="Company A", amount="5000.00")
    _setup_disbursed_loan(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"], amount="20000.00")

    body = client.get("/analytics/dashboard", headers=_auth_headers(ctx_a["admin_token"])).json()
    assert body["portfolio"]["total_disbursed_all_time"] == "5000.00"
    assert body["flows"]["disbursed_amount"] == "5000.00"


def test_user_summary_counts_staff_and_customers(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.get("/admin/users/summary", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # system_administrator + credit_officer + branch_manager + cashier_finance_officer = 4 staff, all active.
    assert body["staff_total"] == 4
    assert body["staff_active"] == 4
    assert body["staff_inactive"] == 0
    assert body["customer_total"] == 1
    assert body["customer_active"] == 1


def test_user_summary_reflects_deactivated_staff(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    staff = client.get("/staff", headers=_auth_headers(ctx["admin_token"])).json()
    officer = next(s for s in staff if s["email"].startswith("compliance@"))
    client.post(f"/staff/{officer['id']}/deactivate", headers=_auth_headers(ctx["admin_token"]))

    resp = client.get("/admin/users/summary", headers=_auth_headers(ctx["admin_token"]))
    body = resp.json()
    assert body["staff_active"] == 3
    assert body["staff_inactive"] == 1


def test_user_summary_is_tenant_isolated(client, engine):
    ctx_a = _setup_disbursed_loan(client, engine, company_name="Company A")
    _setup_disbursed_loan(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"])

    resp = client.get("/admin/users/summary", headers=_auth_headers(ctx_a["admin_token"]))
    assert resp.json()["staff_total"] == 4
    assert resp.json()["customer_total"] == 1


def test_admin_can_create_product(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.post(
        "/admin/products",
        json={
            "name": "Asset Finance",
            "description": "Longer-term asset-backed loan",
            "min_amount": "10000.00",
            "max_amount": "500000.00",
            "interest_rate": "10.00",
            "repayment_period_days": 180,
            "interest_model": "reducing_balance",
            "installment_count": 6,
        },
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Asset Finance"
    assert body["interest_model"] == "reducing_balance"
    assert body["installment_count"] == 6

    names = {p["name"] for p in client.get("/admin/products", headers=_auth_headers(ctx["admin_token"])).json()}
    assert "Asset Finance" in names

    audit = client.get("/admin/audit-log", headers=_auth_headers(ctx["admin_token"])).json()
    assert any(entry["action"] == "loan_product.create" for entry in audit)


def test_create_product_rejects_min_above_max(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.post(
        "/admin/products",
        json={
            "name": "Broken Product",
            "min_amount": "999999.00",
            "max_amount": "1000.00",
            "interest_rate": "5.00",
            "repayment_period_days": 30,
        },
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 400


def test_non_admin_cannot_create_product(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.post(
        "/admin/products",
        json={
            "name": "Sneaky Product",
            "min_amount": "1000.00",
            "max_amount": "5000.00",
            "interest_rate": "5.00",
            "repayment_period_days": 30,
        },
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert resp.status_code == 403


def test_admin_can_delete_an_unused_product(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    created = client.post(
        "/admin/products",
        json={
            "name": "Never Used",
            "min_amount": "1000.00",
            "max_amount": "5000.00",
            "interest_rate": "5.00",
            "repayment_period_days": 30,
        },
        headers=_auth_headers(ctx["admin_token"]),
    ).json()

    resp = client.delete(f"/admin/products/{created['id']}", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 204, resp.text

    names = {p["name"] for p in client.get("/admin/products", headers=_auth_headers(ctx["admin_token"])).json()}
    assert "Never Used" not in names

    audit = client.get("/admin/audit-log", headers=_auth_headers(ctx["admin_token"])).json()
    assert any(entry["action"] == "loan_product.delete" for entry in audit)


def test_admin_cannot_delete_a_product_already_used_by_a_loan(client, engine):
    """CLAUDE.md §12/§13: deleting a referenced product would either violate
    the FK or silently orphan real financial history — neither is
    acceptable. is_active is the correct "retire it" lever once a product
    has actually been used."""
    ctx = _setup_disbursed_loan(client, engine)  # uses "Salary Advance"
    products = client.get("/admin/products", headers=_auth_headers(ctx["admin_token"])).json()
    used_product = next(p for p in products if p["name"] == "Salary Advance")

    resp = client.delete(f"/admin/products/{used_product['id']}", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 409, resp.text

    names = {p["name"] for p in client.get("/admin/products", headers=_auth_headers(ctx["admin_token"])).json()}
    assert "Salary Advance" in names  # still there


def test_admin_cannot_delete_a_product_with_only_an_application(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    products = client.get("/admin/products", headers=_auth_headers(ctx["admin_token"])).json()
    business_loan = next(p for p in products if p["name"] == "Business Loan")

    apply_resp = client.post(
        "/applications",
        json={"loan_product_id": business_loan["id"], "amount_requested": "10000.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    # The customer already has a pending application from _setup_disbursed_loan's
    # own approved+disbursed one only if still pending — here it's already
    # approved/disbursed, so a second application is allowed.
    assert apply_resp.status_code == 201, apply_resp.text

    resp = client.delete(f"/admin/products/{business_loan['id']}", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 409


def test_non_admin_cannot_delete_product(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    products = client.get("/admin/products", headers=_auth_headers(ctx["admin_token"])).json()
    product_id = products[0]["id"]

    resp = client.delete(f"/admin/products/{product_id}", headers=_auth_headers(ctx["credit_token"]))
    assert resp.status_code == 403


def test_cannot_delete_another_companys_product(client, engine):
    ctx_a = _setup_disbursed_loan(client, engine, company_name="Company A")
    ctx_b = _setup_disbursed_loan(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"])
    products_b = client.get("/admin/products", headers=_auth_headers(ctx_b["admin_token"])).json()

    resp = client.delete(f"/admin/products/{products_b[0]['id']}", headers=_auth_headers(ctx_a["admin_token"]))
    assert resp.status_code == 404


def test_loan_calculator_matches_generate_schedule_and_writes_nothing(client, engine):
    """CLAUDE.md §23: the calculator is a pure preview over the exact same
    dispatcher the real approval flow uses, with zero DB writes."""
    ctx = _setup_disbursed_loan(client, engine)
    before_count = None
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            before_count = len(session.exec(select(Loan)).all())

    resp = client.post(
        "/admin/loans/calculator",
        json={
            "principal": "10000.00",
            "interest_rate": "8.00",
            "interest_model": "reducing_balance",
            "term_days": 90,
            "installment_count": 3,
            "start_date": "2026-01-01",
        },
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["schedule"]) == 3

    expected = generate_schedule(
        principal=Decimal("10000.00"),
        rate_percent=Decimal("8.00"),
        interest_model=InterestModel.reducing_balance,
        term_days=90,
        installment_count=3,
        start_date=date(2026, 1, 1),
    )
    assert Decimal(body["total_interest"]) == expected.total_interest
    assert Decimal(body["total_repayable"]) == expected.total_repayable
    for got, want in zip(body["schedule"], expected.installments):
        assert Decimal(got["principal_component"]) == want.principal_component
        assert Decimal(got["interest_component"]) == want.interest_component
        assert got["is_paid"] is False

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            after_count = len(session.exec(select(Loan)).all())
    assert after_count == before_count  # nothing persisted


def test_loan_calculator_requires_system_administrator(client, engine):
    ctx = _setup_disbursed_loan(client, engine)
    resp = client.post(
        "/admin/loans/calculator",
        json={"principal": "1000.00", "interest_rate": "5.00", "term_days": 30},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert resp.status_code == 403


def test_admin_loan_detail_shows_full_schedule(client, engine):
    ctx = _setup_disbursed_loan(client, engine, amount="5000.00")
    resp = client.get(f"/admin/loans/{ctx['loan_id']}", headers=_auth_headers(ctx["admin_token"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["customer_full_name"] == "Customer One"
    assert body["principal"] == "5000.00"
    assert len(body["schedule"]) >= 1
    installment = body["schedule"][0]
    assert set(installment) >= {"due_date", "amount_due", "amount_paid", "principal_component", "interest_component", "is_paid"}


def test_admin_loan_detail_is_tenant_isolated(client, engine):
    ctx_a = _setup_disbursed_loan(client, engine, company_name="Company A")
    ctx_b = _setup_disbursed_loan(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"])

    resp = client.get(f"/admin/loans/{ctx_b['loan_id']}", headers=_auth_headers(ctx_a["admin_token"]))
    assert resp.status_code == 404
