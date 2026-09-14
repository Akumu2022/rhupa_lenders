import io

from tests.conftest import create_branch, seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _submit_profile(client, token, national_id="A123456789"):
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


def _setup_company(client, engine, *, company_name="Company A", platform_token=None):
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

    officer_resp = client.post(
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
    officer_token = _login(client, f"compliance@{slug}.example.com", "compliance-pass-1")

    signup_resp = client.post(
        "/signup",
        json={
            "signup_code": company["signup_code"],
            "email": f"customer@{slug}.example.com",
            "password": "customer-pass-1",
            "full_name": "Customer One",
        },
    )
    assert signup_resp.status_code == 201, signup_resp.text
    customer_token = signup_resp.json()["access_token"]

    return {
        "platform_token": platform_token,
        "admin_token": admin_token,
        "officer_token": officer_token,
        "customer_token": customer_token,
        "company": company,
    }


def _verify_customer_kyc(client, ctx):
    _submit_profile(client, ctx["customer_token"])
    queue = client.get("/compliance/queue", headers=_auth_headers(ctx["officer_token"])).json()
    profile_id = queue[0]["id"]
    resp = client.post(
        f"/compliance/profiles/{profile_id}/verify",
        json={"notes": None},
        headers=_auth_headers(ctx["officer_token"]),
    )
    assert resp.status_code == 200


def test_company_creation_seeds_three_loan_products(client, engine):
    ctx = _setup_company(client, engine)
    resp = client.get("/loan-products", headers=_auth_headers(ctx["customer_token"]))
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert names == {"Salary Advance", "Emergency Loan", "Business Loan"}


def test_loan_products_are_tenant_isolated(client, engine):
    ctx_a = _setup_company(client, engine, company_name="Company A")
    ctx_b = _setup_company(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"])

    products_a = client.get("/loan-products", headers=_auth_headers(ctx_a["customer_token"])).json()
    products_b = client.get("/loan-products", headers=_auth_headers(ctx_b["customer_token"])).json()

    ids_a = {p["id"] for p in products_a}
    ids_b = {p["id"] for p in products_b}
    assert ids_a.isdisjoint(ids_b)


def test_unverified_customer_cannot_apply(client, engine):
    ctx = _setup_company(client, engine)
    products = client.get("/loan-products", headers=_auth_headers(ctx["customer_token"])).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")

    resp = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": "5000.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert resp.status_code == 403


def test_verified_customer_can_apply_within_range(client, engine):
    ctx = _setup_company(client, engine)
    _verify_customer_kyc(client, ctx)

    products = client.get("/loan-products", headers=_auth_headers(ctx["customer_token"])).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")

    resp = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": "5000.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # CLAUDE.md §26 (M13): self-signup never sets branch_id, so this
    # customer's application skips branch review (no branch manager to
    # route it to) and lands straight in committee review.
    assert body["status"] == "pending_committee_review"
    assert body["amount_requested"] == "5000.00"


def test_amount_outside_product_range_is_rejected(client, engine):
    ctx = _setup_company(client, engine)
    _verify_customer_kyc(client, ctx)

    products = client.get("/loan-products", headers=_auth_headers(ctx["customer_token"])).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")

    resp = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": "999999.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert resp.status_code == 400


def test_cannot_apply_to_another_companys_product(client, engine):
    ctx_a = _setup_company(client, engine, company_name="Company A")
    ctx_b = _setup_company(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"])
    _verify_customer_kyc(client, ctx_a)

    products_b = client.get("/loan-products", headers=_auth_headers(ctx_b["customer_token"])).json()
    product_from_b = products_b[0]

    resp = client.post(
        "/applications",
        json={"loan_product_id": product_from_b["id"], "amount_requested": "5000.00"},
        headers=_auth_headers(ctx_a["customer_token"]),
    )
    assert resp.status_code == 404


def test_cannot_submit_second_application_while_one_is_pending(client, engine):
    ctx = _setup_company(client, engine)
    _verify_customer_kyc(client, ctx)
    products = client.get("/loan-products", headers=_auth_headers(ctx["customer_token"])).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")

    first = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": "5000.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert first.status_code == 201

    second = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": "6000.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert second.status_code == 409


def test_customer_can_view_own_applications(client, engine):
    ctx = _setup_company(client, engine)
    _verify_customer_kyc(client, ctx)
    products = client.get("/loan-products", headers=_auth_headers(ctx["customer_token"])).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")

    client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": "5000.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )

    resp = client.get("/applications/me", headers=_auth_headers(ctx["customer_token"]))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["amount_requested"] == "5000.00"


def test_suspended_company_blocks_new_applications(client, engine):
    """CLAUDE.md §6 allow-list: new applications are stopped while suspended
    — this falls out of the central suspension gate automatically since
    customers aren't exempt."""
    ctx = _setup_company(client, engine)
    _verify_customer_kyc(client, ctx)
    products = client.get("/loan-products", headers=_auth_headers(ctx["customer_token"])).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")

    client.post(
        f"/platform/companies/{ctx['company']['id']}/suspend",
        json={"reason": "non-payment"},
        headers=_auth_headers(ctx["platform_token"]),
    )

    resp = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": "5000.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "company_suspended"
