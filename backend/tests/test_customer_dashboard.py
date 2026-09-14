"""CLAUDE.md M6: customer dashboard — loan limit/available credit, active
loans + status + balance, repayment schedule, transaction history, and a
simple standing indicator (never a raw score, per rule #7).
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlmodel import Session, select

from app.models import RepaymentSchedule, User
from app.tenancy import tenant_context
from tests.conftest import create_branch, seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _submit_profile(client, token, national_id="A123456789"):
    import io

    resp = client.post(
        "/profile",
        headers=_auth_headers(token),
        data={
            "date_of_birth": "1995-05-05",
            "national_id_number": national_id,
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
    assert resp.status_code == 201, resp.text
    return resp.json()


def _setup_verified_customer(client, engine, *, company_name="Company A", platform_token=None, email_slug="customer1"):
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

    compliance_resp = client.post(
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
    assert compliance_resp.status_code == 201, compliance_resp.text
    compliance_token = _login(client, f"compliance@{slug}.example.com", "compliance-pass-1")

    credit_resp = client.post(
        "/staff",
        json={
            "email": f"credit@{slug}.example.com",
            "password": "credit-pass-123",
            "full_name": "Credit One",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    )
    assert credit_resp.status_code == 201, credit_resp.text
    credit_token = _login(client, f"credit@{slug}.example.com", "credit-pass-123")

    manager_resp = client.post(
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
    assert manager_resp.status_code == 201, manager_resp.text
    manager_token = _login(client, f"manager@{slug}.example.com", "manager-pass-123")

    signup_resp = client.post(
        "/signup",
        json={
            "signup_code": company["signup_code"],
            "email": f"{email_slug}@{slug}.example.com",
            "password": "customer-pass-1",
            "full_name": "Customer One",
        },
    )
    assert signup_resp.status_code == 201, signup_resp.text
    customer_token = signup_resp.json()["access_token"]

    # CLAUDE.md §7: self-signup never sets branch_id — patched directly here
    # so applications route to branch review (this suite is about the
    # dashboard, not registration mechanics).
    with Session(engine) as session:
        with tenant_context(company["id"]):
            customer = session.exec(select(User).where(User.email == f"{email_slug}@{slug}.example.com")).first()
            customer.branch_id = branch["id"]
            session.add(customer)
            session.commit()

    _submit_profile(client, customer_token, national_id=f"NATID-{email_slug}")
    queue = client.get("/compliance/queue", headers=_auth_headers(compliance_token)).json()
    profile_id = next(p["id"] for p in queue if p["national_id_number"] == f"NATID-{email_slug}")
    verify_resp = client.post(
        f"/compliance/profiles/{profile_id}/verify",
        json={"notes": None},
        headers=_auth_headers(compliance_token),
    )
    assert verify_resp.status_code == 200

    return {
        "platform_token": platform_token,
        "admin_token": admin_token,
        "compliance_token": compliance_token,
        "credit_token": credit_token,
        "manager_token": manager_token,
        "customer_token": customer_token,
        "company": company,
    }


def _apply_and_approve(client, ctx, *, amount="5000.00"):
    products = client.get("/loan-products", headers=_auth_headers(ctx["customer_token"])).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")
    application = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": amount},
        headers=_auth_headers(ctx["customer_token"]),
    ).json()
    approval = client.post(
        f"/branch-manager/applications/{application['id']}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert approval.status_code == 200, approval.text
    return approval.json()


def test_loans_me_before_any_loan_shows_full_limit_and_good_standing(client, engine):
    ctx = _setup_verified_customer(client, engine)
    resp = client.get("/loans/me", headers=_auth_headers(ctx["customer_token"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Highest max_amount among the three seeded products is Business Loan's 200000.00.
    assert body["loan_limit"] == "200000.00"
    assert body["available_credit"] == "200000.00"
    assert body["standing"] == "good_standing"
    assert body["loans"] == []


def test_loans_me_after_approval_lists_loan_with_schedule_and_reduces_available_credit(client, engine):
    ctx = _setup_verified_customer(client, engine)
    approval = _apply_and_approve(client, ctx, amount="5000.00")

    resp = client.get("/loans/me", headers=_auth_headers(ctx["customer_token"]))
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["loans"]) == 1
    loan = body["loans"][0]
    assert loan["loan_product_name"] == "Salary Advance"
    assert loan["principal"] == "5000.00"
    assert loan["total_repayable"] == "5250.00"
    assert loan["outstanding_balance"] == "5250.00"
    assert loan["status"] == "approved"
    assert len(loan["schedule"]) == 1
    assert loan["schedule"][0]["amount_due"] == "5250.00"
    assert loan["schedule"][0]["is_paid"] is False

    # 200000.00 limit - 5250.00 outstanding on the new loan.
    assert body["available_credit"] == "194750.00"
    assert body["standing"] == "good_standing"
    # branch-manager decide returns the application view (loan_status), not
    # a nested loan object.
    assert approval["loan_status"] == "approved"


def test_standing_flips_to_attention_needed_when_installment_is_overdue(client, engine):
    ctx = _setup_verified_customer(client, engine)
    _apply_and_approve(client, ctx, amount="5000.00")

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            schedule = session.exec(select(RepaymentSchedule)).first()
            schedule.due_date = date.today() - timedelta(days=1)
            session.add(schedule)
            session.commit()

    resp = client.get("/loans/me", headers=_auth_headers(ctx["customer_token"]))
    assert resp.status_code == 200
    assert resp.json()["standing"] == "attention_needed"


def test_transactions_me_is_empty_until_disbursement_ships(client, engine):
    """M7 is what writes ledger rows; M6 only reads the (currently empty) table."""
    ctx = _setup_verified_customer(client, engine)
    resp = client.get("/transactions/me", headers=_auth_headers(ctx["customer_token"]))
    assert resp.status_code == 200
    assert resp.json() == []


def test_customer_cannot_see_another_customers_loans(client, engine):
    ctx = _setup_verified_customer(client, engine, email_slug="customer1")

    signup_resp = client.post(
        "/signup",
        json={
            "signup_code": ctx["company"]["signup_code"],
            "email": f"customer2@{ctx['company']['name'].lower().replace(' ', '')}.example.com",
            "password": "customer-pass-2",
            "full_name": "Customer Two",
        },
    )
    assert signup_resp.status_code == 201, signup_resp.text
    other_customer_token = signup_resp.json()["access_token"]

    _apply_and_approve(client, ctx, amount="5000.00")

    resp = client.get("/loans/me", headers=_auth_headers(other_customer_token))
    assert resp.status_code == 200
    assert resp.json()["loans"] == []


def test_non_customer_roles_cannot_access_loans_me_or_transactions_me(client, engine):
    ctx = _setup_verified_customer(client, engine)

    for token in (ctx["admin_token"], ctx["compliance_token"], ctx["credit_token"]):
        loans_resp = client.get("/loans/me", headers=_auth_headers(token))
        assert loans_resp.status_code == 403

        tx_resp = client.get("/transactions/me", headers=_auth_headers(token))
        assert tx_resp.status_code == 403
