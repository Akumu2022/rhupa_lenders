import io

from tests.conftest import create_branch, seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_company_and_signup_customer(
    client, engine, company_name="Company A", customer_email="cust@a.example.com", platform_token=None
):
    if platform_token is None:
        seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
        platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = client.post(
        "/platform/companies",
        json={
            "name": company_name,
            "admin_email": f"admin@{company_name.lower().replace(' ', '')}.example.com",
            "admin_password": "admin-pass-123",
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    ).json()

    signup_resp = client.post(
        "/signup",
        json={
            "signup_code": company["signup_code"],
            "email": customer_email,
            "password": "customer-pass-1",
            "full_name": "Customer One",
        },
    )
    assert signup_resp.status_code == 201, signup_resp.text
    customer_token = signup_resp.json()["access_token"]
    return company, customer_token, platform_token


def _submit_profile(client, token, *, national_id="A123456789"):
    return client.post(
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


def test_customer_can_submit_profile(client, engine):
    _, customer_token, _ = _create_company_and_signup_customer(client, engine)

    resp = _submit_profile(client, customer_token)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kyc_status"] == "pending"
    assert body["national_id_number"] == "A123456789"
    assert "reviewed_by" not in body  # CLAUDE.md §9: never expose reviewer identity


def test_customer_can_view_own_profile(client, engine):
    _, customer_token, _ = _create_company_and_signup_customer(client, engine)
    _submit_profile(client, customer_token)

    resp = client.get("/profile", headers=_auth_headers(customer_token))
    assert resp.status_code == 200
    assert resp.json()["kyc_status"] == "pending"


def test_profile_lookup_404_before_submission(client, engine):
    _, customer_token, _ = _create_company_and_signup_customer(client, engine)
    resp = client.get("/profile", headers=_auth_headers(customer_token))
    assert resp.status_code == 404


def test_cannot_resubmit_while_pending(client, engine):
    _, customer_token, _ = _create_company_and_signup_customer(client, engine)
    first = _submit_profile(client, customer_token)
    assert first.status_code == 201

    second = _submit_profile(client, customer_token, national_id="DIFFERENT-ID")
    assert second.status_code == 409


def test_rejects_unsupported_file_type(client, engine):
    _, customer_token, _ = _create_company_and_signup_customer(client, engine)

    resp = client.post(
        "/profile",
        headers=_auth_headers(customer_token),
        data={
            "date_of_birth": "1995-05-05",
            "national_id_number": "A123456789",
            "phone_number": "+254700000000",
            "residential_address": "123 Main St",
            "employment_status": "employed",
            "monthly_income": "45000.00",
            "occupation": "Engineer",
        },
        files={
            "id_document": ("id.exe", io.BytesIO(b"not-an-image"), "application/octet-stream"),
            "id_document_back": ("id-back.jpg", io.BytesIO(b"fake-image-bytes-back"), "image/jpeg"),
        },
    )
    assert resp.status_code == 400


def test_id_document_back_is_required(client, engine):
    _, customer_token, _ = _create_company_and_signup_customer(client, engine)

    resp = client.post(
        "/profile",
        headers=_auth_headers(customer_token),
        data={
            "date_of_birth": "1995-05-05",
            "national_id_number": "A123456789",
            "phone_number": "+254700000000",
            "residential_address": "123 Main St",
            "employment_status": "employed",
            "monthly_income": "45000.00",
            "occupation": "Engineer",
        },
        files={"id_document": ("id-front.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
    )
    assert resp.status_code == 422


def test_non_customer_cannot_submit_profile(client, engine):
    _, _, platform_token = _create_company_and_signup_customer(client, engine)
    resp = _submit_profile(client, platform_token)
    assert resp.status_code == 403


def test_profile_is_isolated_per_company(client, engine):
    """A staff member of Company A's staff endpoints never surface Company B's
    profile — proven here at the API layer, on top of the ORM-level suite in
    test_tenant_isolation.py."""
    _, customer_a_token, platform_token = _create_company_and_signup_customer(
        client, engine, company_name="Company A", customer_email="a@a.example.com"
    )
    _, customer_b_token, _ = _create_company_and_signup_customer(
        client, engine, company_name="Company B", customer_email="b@b.example.com", platform_token=platform_token
    )

    _submit_profile(client, customer_a_token, national_id="A-ID")
    _submit_profile(client, customer_b_token, national_id="B-ID")

    resp_a = client.get("/profile", headers=_auth_headers(customer_a_token))
    resp_b = client.get("/profile", headers=_auth_headers(customer_b_token))

    assert resp_a.json()["national_id_number"] == "A-ID"
    assert resp_b.json()["national_id_number"] == "B-ID"


def test_resubmit_after_override_is_a_conflict_and_does_not_clobber_it(client, engine):
    """CLAUDE.md §14: the resubmit-after-rejection path must be a guarded
    compare-and-set, not a blind UPDATE. Proven here: a system_administrator
    override moves a rejected profile to verified; the customer's in-flight
    resubmit (which only knew about the rejection) must now get 409 instead
    of silently overwriting the override back to pending."""
    company, customer_token, platform_token = _create_company_and_signup_customer(client, engine)
    admin_token = _login(client, "admin@companya.example.com", "admin-pass-123")
    branch = create_branch(client, admin_token)

    officer_resp = client.post(
        "/staff",
        json={
            "email": "credit@companya.example.com",
            "password": "credit-pass-123",
            "full_name": "Credit One",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    )
    assert officer_resp.status_code == 201, officer_resp.text
    officer_token = _login(client, "credit@companya.example.com", "credit-pass-123")

    submit_resp = _submit_profile(client, customer_token)
    profile_id = submit_resp.json()["id"]

    reject_resp = client.post(
        f"/compliance/profiles/{profile_id}/reject",
        json={"reason": "Blurry ID"},
        headers=_auth_headers(officer_token),
    )
    assert reject_resp.status_code == 200, reject_resp.text

    # Someone else (system_administrator) already moved this profile off
    # `rejected` before the customer's resubmit lands.
    override_resp = client.post(
        f"/admin/kyc/{profile_id}/override",
        json={"new_status": "verified", "reason": "Manually confirmed by phone"},
        headers=_auth_headers(admin_token),
    )
    assert override_resp.status_code == 200, override_resp.text

    resubmit_resp = _submit_profile(client, customer_token, national_id="NEW-ID-AFTER-REJECT")
    assert resubmit_resp.status_code == 409, resubmit_resp.text

    # The override must survive untouched — not clobbered back to pending.
    current = client.get("/profile", headers=_auth_headers(customer_token))
    assert current.json()["kyc_status"] == "verified"
    assert current.json()["national_id_number"] == "A123456789"  # unchanged by the failed resubmit
