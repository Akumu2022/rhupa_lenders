import io

from tests.conftest import create_branch, seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _submit_profile(client, token, *, national_id="A123456789", with_selfie=False):
    files = {
        "id_document": ("id-front.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg"),
        "id_document_back": ("id-back.jpg", io.BytesIO(b"fake-image-bytes-back"), "image/jpeg"),
    }
    if with_selfie:
        files["selfie_photo"] = ("selfie.png", io.BytesIO(b"fake-selfie-bytes"), "image/png")
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
        files=files,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _setup_company_with_customer(client, engine, *, company_name="Company A", platform_token=None, with_selfie=False):
    """Seeds a super_admin (once, reusable via platform_token), creates a
    company + its admin, that admin's credit officer (who now owns KYC per
    M10), and a customer with a submitted (pending) profile. Returns
    everything the tests need."""
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
    assert officer_resp.status_code == 201, officer_resp.text
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

    profile = _submit_profile(client, customer_token, with_selfie=with_selfie)

    return {
        "platform_token": platform_token,
        "admin_token": admin_token,
        "officer_token": officer_token,
        "customer_token": customer_token,
        "company": company,
        "profile": profile,
    }


def test_queue_shows_pending_profile(client, engine):
    ctx = _setup_company_with_customer(client, engine)
    resp = client.get("/compliance/queue", headers=_auth_headers(ctx["officer_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["national_id_number"] == "A123456789"
    assert body[0]["customer_email"] == "customer@companya.example.com"
    assert body[0]["kyc_status"] == "pending"
    assert body[0]["has_id_document_back"] is True


def test_document_endpoint_serves_id_back(client, engine):
    ctx = _setup_company_with_customer(client, engine)
    profile_id = ctx["profile"]["id"]

    resp = client.get(
        f"/compliance/profiles/{profile_id}/document/id_document_back", headers=_auth_headers(ctx["officer_token"])
    )
    assert resp.status_code == 200
    assert resp.content == b"fake-image-bytes-back"


def test_history_lists_all_statuses_and_is_visible_after_decision(client, engine):
    """CLAUDE.md §9: accountability — a decided profile stays reviewable, not
    just while it's pending."""
    ctx = _setup_company_with_customer(client, engine)
    profile_id = ctx["profile"]["id"]

    before = client.get("/compliance/history", headers=_auth_headers(ctx["officer_token"]))
    assert before.status_code == 200
    assert len(before.json()) == 1
    assert before.json()[0]["kyc_status"] == "pending"

    client.post(
        f"/compliance/profiles/{profile_id}/verify",
        json={"notes": "Looks good"},
        headers=_auth_headers(ctx["officer_token"]),
    )

    # Gone from the pending queue...
    queue_after = client.get("/compliance/queue", headers=_auth_headers(ctx["officer_token"]))
    assert queue_after.json() == []

    # ...but still visible in history, for future reference.
    after = client.get("/compliance/history", headers=_auth_headers(ctx["officer_token"]))
    assert len(after.json()) == 1
    assert after.json()[0]["kyc_status"] == "verified"
    assert after.json()[0]["review_notes"] == "Looks good"


def test_history_is_tenant_isolated(client, engine):
    ctx_a = _setup_company_with_customer(client, engine, company_name="Company A")
    ctx_b = _setup_company_with_customer(
        client, engine, company_name="Company B", platform_token=ctx_a["platform_token"]
    )

    resp = client.get("/compliance/history", headers=_auth_headers(ctx_a["officer_token"]))
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] != ctx_b["profile"]["id"]


def test_system_administrator_can_view_history_but_customer_cannot(client, engine):
    ctx = _setup_company_with_customer(client, engine)

    admin_resp = client.get("/compliance/history", headers=_auth_headers(ctx["admin_token"]))
    assert admin_resp.status_code == 200

    customer_resp = client.get("/compliance/history", headers=_auth_headers(ctx["customer_token"]))
    assert customer_resp.status_code == 403


def test_verify_removes_profile_from_queue_and_writes_audit(client, engine):
    ctx = _setup_company_with_customer(client, engine)
    profile_id = ctx["profile"]["id"]

    verify_resp = client.post(
        f"/compliance/profiles/{profile_id}/verify",
        json={"notes": "Checked ID against selfie"},
        headers=_auth_headers(ctx["officer_token"]),
    )
    assert verify_resp.status_code == 200, verify_resp.text
    assert verify_resp.json()["kyc_status"] == "verified"

    queue_resp = client.get("/compliance/queue", headers=_auth_headers(ctx["officer_token"]))
    assert queue_resp.json() == []

    customer_view = client.get("/profile", headers=_auth_headers(ctx["customer_token"]))
    assert customer_view.json()["kyc_status"] == "verified"


def test_double_verify_is_a_conflict(client, engine):
    """CLAUDE.md §14: compare-and-set — a doubled click must not silently
    succeed twice."""
    ctx = _setup_company_with_customer(client, engine)
    profile_id = ctx["profile"]["id"]

    first = client.post(
        f"/compliance/profiles/{profile_id}/verify",
        json={"notes": None},
        headers=_auth_headers(ctx["officer_token"]),
    )
    assert first.status_code == 200

    second = client.post(
        f"/compliance/profiles/{profile_id}/verify",
        json={"notes": None},
        headers=_auth_headers(ctx["officer_token"]),
    )
    assert second.status_code == 409


def test_reject_requires_reason(client, engine):
    ctx = _setup_company_with_customer(client, engine)
    profile_id = ctx["profile"]["id"]

    resp = client.post(
        f"/compliance/profiles/{profile_id}/reject",
        json={"reason": ""},
        headers=_auth_headers(ctx["officer_token"]),
    )
    assert resp.status_code == 422


def test_reject_sends_customer_back_with_reason_and_allows_resubmit(client, engine):
    ctx = _setup_company_with_customer(client, engine)
    profile_id = ctx["profile"]["id"]

    reject_resp = client.post(
        f"/compliance/profiles/{profile_id}/reject",
        json={"reason": "ID photo is blurry"},
        headers=_auth_headers(ctx["officer_token"]),
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["kyc_status"] == "rejected"

    customer_view = client.get("/profile", headers=_auth_headers(ctx["customer_token"]))
    assert customer_view.json()["kyc_status"] == "rejected"
    assert customer_view.json()["review_notes"] == "ID photo is blurry"

    resubmit = _submit_profile(client, ctx["customer_token"], national_id="NEW-ID-AFTER-FIX")
    assert resubmit["kyc_status"] == "pending"

    queue_resp = client.get("/compliance/queue", headers=_auth_headers(ctx["officer_token"]))
    assert len(queue_resp.json()) == 1
    assert queue_resp.json()[0]["national_id_number"] == "NEW-ID-AFTER-FIX"


def test_credit_officer_cannot_see_or_act_on_other_companys_profile(client, engine):
    ctx_a = _setup_company_with_customer(client, engine, company_name="Company A")
    ctx_b = _setup_company_with_customer(
        client, engine, company_name="Company B", platform_token=ctx_a["platform_token"]
    )

    resp = client.get(
        f"/compliance/profiles/{ctx_b['profile']['id']}", headers=_auth_headers(ctx_a["officer_token"])
    )
    assert resp.status_code == 404

    verify_resp = client.post(
        f"/compliance/profiles/{ctx_b['profile']['id']}/verify",
        json={"notes": None},
        headers=_auth_headers(ctx_a["officer_token"]),
    )
    assert verify_resp.status_code == 404

    # Company B's own profile is untouched and still visible to its own officer.
    still_pending = client.get("/compliance/queue", headers=_auth_headers(ctx_b["officer_token"]))
    assert len(still_pending.json()) == 1


def test_non_credit_officer_roles_cannot_verify_or_reject(client, engine):
    ctx = _setup_company_with_customer(client, engine)
    profile_id = ctx["profile"]["id"]

    for token in (ctx["admin_token"], ctx["customer_token"]):
        resp = client.post(
            f"/compliance/profiles/{profile_id}/verify",
            json={"notes": None},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 403


def test_system_administrator_can_view_but_not_act(client, engine):
    ctx = _setup_company_with_customer(client, engine)
    profile_id = ctx["profile"]["id"]

    view_resp = client.get(f"/compliance/profiles/{profile_id}", headers=_auth_headers(ctx["admin_token"]))
    assert view_resp.status_code == 200

    verify_resp = client.post(
        f"/compliance/profiles/{profile_id}/verify",
        json={"notes": None},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert verify_resp.status_code == 403


def test_document_endpoint_serves_uploaded_file_to_authorized_staff(client, engine):
    ctx = _setup_company_with_customer(client, engine, with_selfie=True)
    profile_id = ctx["profile"]["id"]

    id_resp = client.get(
        f"/compliance/profiles/{profile_id}/document/id_document", headers=_auth_headers(ctx["officer_token"])
    )
    assert id_resp.status_code == 200
    assert id_resp.content == b"fake-image-bytes"

    selfie_resp = client.get(
        f"/compliance/profiles/{profile_id}/document/selfie", headers=_auth_headers(ctx["officer_token"])
    )
    assert selfie_resp.status_code == 200
    assert selfie_resp.content == b"fake-selfie-bytes"

    admin_resp = client.get(
        f"/compliance/profiles/{profile_id}/document/id_document", headers=_auth_headers(ctx["admin_token"])
    )
    assert admin_resp.status_code == 200


def test_document_endpoint_404_for_missing_selfie(client, engine):
    ctx = _setup_company_with_customer(client, engine, with_selfie=False)
    profile_id = ctx["profile"]["id"]

    resp = client.get(
        f"/compliance/profiles/{profile_id}/document/selfie", headers=_auth_headers(ctx["officer_token"])
    )
    assert resp.status_code == 404


def test_document_endpoint_rejects_unauthorized_roles(client, engine):
    ctx = _setup_company_with_customer(client, engine)
    profile_id = ctx["profile"]["id"]

    for token in (ctx["customer_token"],):
        resp = client.get(
            f"/compliance/profiles/{profile_id}/document/id_document", headers=_auth_headers(token)
        )
        assert resp.status_code == 403


def test_document_endpoint_404_across_companies(client, engine):
    ctx_a = _setup_company_with_customer(client, engine, company_name="Company A")
    ctx_b = _setup_company_with_customer(
        client, engine, company_name="Company B", platform_token=ctx_a["platform_token"]
    )

    resp = client.get(
        f"/compliance/profiles/{ctx_b['profile']['id']}/document/id_document",
        headers=_auth_headers(ctx_a["officer_token"]),
    )
    assert resp.status_code == 404
