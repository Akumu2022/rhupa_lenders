import io
from decimal import Decimal

import app.routers.customers as customers_module
from sqlmodel import Session

from app.models import BusinessAssessment
from app.tenancy import tenant_context
from tests.conftest import create_branch, seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_company_with_credit_officer(client, engine, *, company_name="Company A", platform_token=None):
    """Seeds a super_admin (once, reusable), a company + its system_administrator,
    a branch, and a credit_officer assigned to that branch."""
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

    branch = create_branch(client, admin_token, name=f"{company_name} Main", code="MAIN")

    officer_resp = client.post(
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
    assert officer_resp.status_code == 201, officer_resp.text
    officer_token = _login(client, f"credit@{slug}.example.com", "credit-pass-123")

    return {
        "platform_token": platform_token,
        "admin_token": admin_token,
        "officer_token": officer_token,
        "company": company,
        "branch": branch,
    }


def _register_customer(client, officer_token, *, email="new.customer@a.example.com", national_id="REG-ID-1"):
    return client.post(
        "/customers",
        headers=_auth_headers(officer_token),
        data={
            "email": email,
            "password": "customer-pass-1",
            "full_name": "New Customer",
            "first_name": "New",
            "last_name": "Customer",
            "id_type": "national_id",
            "national_id_number": national_id,
            "date_of_birth": "1990-01-01",
            "gender": "female",
            "nationality": "Kenyan",
            "marital_status": "single",
            "dependants_count": "2",
            "phone_number": "+254700000111",
            "residential_address": "456 Branch Rd",
            "employment_status": "self_employed",
            "occupation": "Trader",
            "monthly_income": "30000.00",
            "next_of_kin_name": "Jane Doe",
            "next_of_kin_relationship": "Sister",
            "next_of_kin_phone": "+254700000222",
        },
        files={
            "id_document": ("id-front.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg"),
            "id_document_back": ("id-back.jpg", io.BytesIO(b"fake-image-bytes-back"), "image/jpeg"),
        },
    )


def test_credit_officer_can_register_customer(client, engine):
    ctx = _setup_company_with_credit_officer(client, engine)

    resp = _register_customer(client, ctx["officer_token"])
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kyc_status"] == "pending"
    assert body["branch_id"] == ctx["branch"]["id"]
    assert body["customer_number"] == f"CUST-{ctx['company']['id']:04d}-000001"


def test_customer_numbers_increment_sequentially_per_company(client, engine):
    ctx = _setup_company_with_credit_officer(client, engine)

    first = _register_customer(client, ctx["officer_token"], email="one@a.example.com", national_id="ID-1")
    second = _register_customer(client, ctx["officer_token"], email="two@a.example.com", national_id="ID-2")

    assert first.json()["customer_number"] == f"CUST-{ctx['company']['id']:04d}-000001"
    assert second.json()["customer_number"] == f"CUST-{ctx['company']['id']:04d}-000002"


def test_registered_customer_can_log_in(client, engine):
    ctx = _setup_company_with_credit_officer(client, engine)
    _register_customer(client, ctx["officer_token"], email="loginme@a.example.com")

    token = _login(client, "loginme@a.example.com", "customer-pass-1")
    resp = client.get("/profile", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["first_name"] == "New"


def test_duplicate_email_rejected(client, engine):
    ctx = _setup_company_with_credit_officer(client, engine)
    _register_customer(client, ctx["officer_token"], email="dupe@a.example.com")

    second = _register_customer(client, ctx["officer_token"], email="dupe@a.example.com", national_id="OTHER-ID")
    assert second.status_code == 409


def test_non_credit_officer_cannot_register_customer(client, engine):
    ctx = _setup_company_with_credit_officer(client, engine)

    resp = _register_customer(client, ctx["admin_token"], email="blocked@a.example.com")
    assert resp.status_code == 403


def test_customer_list_scoped_to_officers_own_branch(client, engine):
    ctx = _setup_company_with_credit_officer(client, engine)
    other_branch = create_branch(client, ctx["admin_token"], name="Other Branch", code="OTHER")
    other_officer_resp = client.post(
        "/staff",
        json={
            "email": "other.credit@companya.example.com",
            "password": "credit-pass-123",
            "full_name": "Other Credit",
            "role": "credit_officer",
            "branch_id": other_branch["id"],
        },
        headers=_auth_headers(ctx["admin_token"]),
    )
    other_officer_token = _login(client, "other.credit@companya.example.com", "credit-pass-123")

    _register_customer(client, ctx["officer_token"], email="mainbranch@a.example.com")
    _register_customer(client, other_officer_token, email="otherbranch@a.example.com")

    main_list = client.get("/customers", headers=_auth_headers(ctx["officer_token"]))
    assert main_list.status_code == 200
    assert [c["email"] for c in main_list.json()] == ["mainbranch@a.example.com"]

    admin_list = client.get("/customers", headers=_auth_headers(ctx["admin_token"]))
    assert {c["email"] for c in admin_list.json()} == {"mainbranch@a.example.com", "otherbranch@a.example.com"}


def test_customer_detail_is_tenant_isolated(client, engine):
    ctx_a = _setup_company_with_credit_officer(client, engine, company_name="Company A")
    ctx_b = _setup_company_with_credit_officer(
        client, engine, company_name="Company B", platform_token=ctx_a["platform_token"]
    )
    created_b = _register_customer(client, ctx_b["officer_token"], email="b.customer@b.example.com").json()

    resp = client.get(f"/customers/{created_b['id']}", headers=_auth_headers(ctx_a["officer_token"]))
    assert resp.status_code == 404


def test_business_assessment_computes_net_income_and_debt_service_capacity(client, engine):
    ctx = _setup_company_with_credit_officer(client, engine)
    customer = _register_customer(client, ctx["officer_token"]).json()

    resp = client.patch(
        f"/customers/{customer['id']}/business-assessment",
        headers=_auth_headers(ctx["officer_token"]),
        json={
            "business_name": "Jane's Kiosk",
            "business_type": "Retail",
            "ownership": "Sole proprietor",
            "physical_location": "Market Stall 12",
            "years_in_operation": 3,
            "sales_frequency": "monthly",
            "total_income": "80000.00",
            "total_expenses": "50000.00",
            "existing_debt_obligations": "10000.00",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["net_income"] == "30000.00"
    assert body["debt_service_capacity"] == "20000.00"


def test_business_assessment_ignores_client_supplied_computed_fields(client, engine):
    ctx = _setup_company_with_credit_officer(client, engine)
    customer = _register_customer(client, ctx["officer_token"]).json()

    resp = client.patch(
        f"/customers/{customer['id']}/business-assessment",
        headers=_auth_headers(ctx["officer_token"]),
        json={
            "business_name": "Jane's Kiosk",
            "business_type": "Retail",
            "ownership": "Sole proprietor",
            "physical_location": "Market Stall 12",
            "years_in_operation": 3,
            "sales_frequency": "monthly",
            "total_income": "80000.00",
            "total_expenses": "50000.00",
            "existing_debt_obligations": "10000.00",
            # Pydantic's extra fields are ignored by default — this proves
            # the server computes these, not whatever a client sends.
            "net_income": "999999.00",
            "debt_service_capacity": "999999.00",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["net_income"] == "30000.00"
    assert body["debt_service_capacity"] == "20000.00"


def test_business_assessment_upsert_updates_in_place(client, engine):
    ctx = _setup_company_with_credit_officer(client, engine)
    customer = _register_customer(client, ctx["officer_token"]).json()

    base_payload = {
        "business_name": "Jane's Kiosk",
        "business_type": "Retail",
        "ownership": "Sole proprietor",
        "physical_location": "Market Stall 12",
        "years_in_operation": 3,
        "sales_frequency": "monthly",
        "total_income": "80000.00",
        "total_expenses": "50000.00",
        "existing_debt_obligations": "10000.00",
    }
    first = client.patch(
        f"/customers/{customer['id']}/business-assessment",
        headers=_auth_headers(ctx["officer_token"]),
        json=base_payload,
    )
    assert first.status_code == 200
    first_id = first.json()["id"]

    updated_payload = {**base_payload, "total_expenses": "60000.00"}
    second = client.patch(
        f"/customers/{customer['id']}/business-assessment",
        headers=_auth_headers(ctx["officer_token"]),
        json=updated_payload,
    )
    assert second.status_code == 200
    assert second.json()["id"] == first_id  # same row, updated — not a new one
    assert second.json()["net_income"] == "20000.00"


def test_business_assessment_404_before_creation(client, engine):
    ctx = _setup_company_with_credit_officer(client, engine)
    customer = _register_customer(client, ctx["officer_token"]).json()

    resp = client.get(f"/customers/{customer['id']}/business-assessment", headers=_auth_headers(ctx["officer_token"]))
    assert resp.status_code == 404


def test_business_assessment_concurrent_create_returns_409_not_500(client, engine, monkeypatch):
    """Simulates two requests racing to create the first BusinessAssessment
    for the same customer: both read 'no assessment yet', both attempt to
    insert. The loser must get a clean 409 from the unique-constraint
    violation, never an unhandled 500 (CLAUDE.md §14 fail-closed discipline)."""
    ctx = _setup_company_with_credit_officer(client, engine)
    customer = _register_customer(client, ctx["officer_token"]).json()

    # A competing row lands first — as if a concurrent request's create won
    # the race.
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            session.add(
                BusinessAssessment(
                    profile_id=customer["profile_id"],
                    company_id=ctx["company"]["id"],
                    business_name="Existing",
                    business_type="Retail",
                    ownership="Sole proprietor",
                    physical_location="Market Stall 1",
                    years_in_operation=1,
                    sales_frequency="monthly",
                    total_income=Decimal("1000.00"),
                    total_expenses=Decimal("500.00"),
                    existing_debt_obligations=Decimal("0.00"),
                    net_income=Decimal("500.00"),
                    debt_service_capacity=Decimal("500.00"),
                )
            )
            session.commit()

    # Force this request's own existence-check to report "not found" anyway
    # — exactly what it would have seen had it read just before the insert
    # above landed.
    monkeypatch.setattr(customers_module, "_get_existing_business_assessment", lambda session, profile_id: None)

    resp = client.patch(
        f"/customers/{customer['id']}/business-assessment",
        headers=_auth_headers(ctx["officer_token"]),
        json={
            "business_name": "Jane's Kiosk",
            "business_type": "Retail",
            "ownership": "Sole proprietor",
            "physical_location": "Market Stall 12",
            "years_in_operation": 3,
            "sales_frequency": "monthly",
            "total_income": "80000.00",
            "total_expenses": "50000.00",
            "existing_debt_obligations": "10000.00",
        },
    )
    assert resp.status_code == 409, resp.text


def test_referees_can_be_added_and_listed(client, engine):
    ctx = _setup_company_with_credit_officer(client, engine)
    customer = _register_customer(client, ctx["officer_token"]).json()

    add_resp = client.post(
        f"/customers/{customer['id']}/referees",
        headers=_auth_headers(ctx["officer_token"]),
        json={"full_name": "Referee One", "phone_number": "+254700000333", "relationship": "Friend"},
    )
    assert add_resp.status_code == 201, add_resp.text

    list_resp = client.get(f"/customers/{customer['id']}/referees", headers=_auth_headers(ctx["officer_token"]))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["full_name"] == "Referee One"


def test_self_signup_profile_still_works_and_gets_customer_number(client, engine):
    """CLAUDE.md §27: the self-signup path (M1/M2) must keep working
    unchanged, and also gets a customer_number on first submission."""
    seed_super_admin(engine, email="platform2@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform2@rupha.example.com", "platform-pass-1")
    company = client.post(
        "/platform/companies",
        json={
            "name": "Self Signup Co",
            "admin_email": "admin@selfsignup.example.com",
            "admin_password": "admin-pass-123",
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    ).json()

    signup_resp = client.post(
        "/signup",
        json={
            "signup_code": company["signup_code"],
            "email": "selfsignup@selfsignup.example.com",
            "password": "customer-pass-1",
            "full_name": "Self Signup Customer",
        },
    )
    customer_token = signup_resp.json()["access_token"]

    submit_resp = client.post(
        "/profile",
        headers=_auth_headers(customer_token),
        data={
            "date_of_birth": "1995-05-05",
            "national_id_number": "SELF-ID-1",
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
    assert submit_resp.status_code == 201, submit_resp.text
    assert submit_resp.json()["customer_number"] == f"CUST-{company['id']:04d}-000001"
