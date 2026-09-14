"""CLAUDE.md §8: system_administrator override — exceptional, reasoned,
distinctly audited, and never mandatory. The anomaly guard flags the same
admin overriding both a KYC decision and a loan decision on the same
applicant.
"""

import io

from sqlmodel import Session, select

from app.models import User
from app.tenancy import tenant_context
from tests.conftest import create_branch, seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


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
    # One credit_officer (not two, as before M13) — fewer logins.
    credit_token = compliance_token

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

    return {
        "platform_token": platform_token,
        "admin_token": admin_token,
        "compliance_token": compliance_token,
        "credit_token": credit_token,
        "manager_token": manager_token,
        "company": company,
        "branch": branch,
        "slug": slug,
    }


def _signup_and_submit_profile(client, ctx, engine, *, email_slug="customer1", national_id="NATID-1"):
    signup_resp = client.post(
        "/signup",
        json={
            "signup_code": ctx["company"]["signup_code"],
            "email": f"{email_slug}@{ctx['slug']}.example.com",
            "password": "customer-pass-1",
            "full_name": "Customer One",
        },
    )
    assert signup_resp.status_code == 201, signup_resp.text
    customer_token = signup_resp.json()["access_token"]

    # CLAUDE.md §7: self-signup never sets branch_id — patched directly here
    # so applications route to branch review (this suite is about override
    # behavior, not registration mechanics).
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            customer = session.exec(
                select(User).where(User.email == f"{email_slug}@{ctx['slug']}.example.com")
            ).first()
            customer.branch_id = ctx["branch"]["id"]
            session.add(customer)
            session.commit()

    client.post(
        "/profile",
        headers=_auth_headers(customer_token),
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
    return customer_token


def test_kyc_override_revokes_a_verification(client, engine):
    ctx = _setup_company(client, engine)
    customer_token = _signup_and_submit_profile(client, ctx, engine)

    queue = client.get("/compliance/queue", headers=_auth_headers(ctx["compliance_token"])).json()
    profile_id = queue[0]["id"]
    client.post(f"/compliance/profiles/{profile_id}/verify", json={"notes": None}, headers=_auth_headers(ctx["compliance_token"]))

    resp = client.post(
        f"/admin/kyc/{profile_id}/override",
        json={"new_status": "rejected", "reason": "Fraud suspected on re-review"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["kyc_status"] == "rejected"

    profile_view = client.get("/profile", headers=_auth_headers(customer_token))
    assert profile_view.json()["kyc_status"] == "rejected"

    audit = client.get("/admin/audit-log", headers=_auth_headers(ctx["admin_token"])).json()
    override_entry = next(e for e in audit if e["action"] == "kyc.override")
    assert "Fraud suspected" in override_entry["reason"]
    assert "verified to rejected" in override_entry["reason"]
    assert override_entry["is_anomaly"] is False


def test_kyc_override_cannot_act_on_pending_profile(client, engine):
    ctx = _setup_company(client, engine)
    _signup_and_submit_profile(client, ctx, engine)
    queue = client.get("/compliance/queue", headers=_auth_headers(ctx["compliance_token"])).json()
    profile_id = queue[0]["id"]

    resp = client.post(
        f"/admin/kyc/{profile_id}/override",
        json={"new_status": "verified", "reason": "Skipping review"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 400


def test_kyc_override_requires_reason(client, engine):
    ctx = _setup_company(client, engine)
    _signup_and_submit_profile(client, ctx, engine)
    queue = client.get("/compliance/queue", headers=_auth_headers(ctx["compliance_token"])).json()
    profile_id = queue[0]["id"]
    client.post(f"/compliance/profiles/{profile_id}/verify", json={"notes": None}, headers=_auth_headers(ctx["compliance_token"]))

    resp = client.post(
        f"/admin/kyc/{profile_id}/override",
        json={"new_status": "rejected", "reason": ""},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 422


def test_application_override_reactivates_rejected_application_and_creates_loan(client, engine):
    ctx = _setup_company(client, engine)
    customer_token = _signup_and_submit_profile(client, ctx, engine)
    queue = client.get("/compliance/queue", headers=_auth_headers(ctx["compliance_token"])).json()
    profile_id = queue[0]["id"]
    client.post(f"/compliance/profiles/{profile_id}/verify", json={"notes": None}, headers=_auth_headers(ctx["compliance_token"]))

    products = client.get("/loan-products", headers=_auth_headers(customer_token)).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")
    application = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": "5000.00"},
        headers=_auth_headers(customer_token),
    ).json()
    client.post(
        f"/branch-manager/applications/{application['id']}/decide",
        json={"decision": "reject", "comments": "Insufficient documentation"},
        headers=_auth_headers(ctx["manager_token"]),
    )

    resp = client.post(
        f"/admin/applications/{application['id']}/override",
        json={"reason": "Documentation was actually complete, officer error"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["application"]["status"] == "approved"
    assert body["loan"]["principal"] == "5000.00"
    assert body["loan"]["total_repayable"] == "5250.00"

    loans_me = client.get("/loans/me", headers=_auth_headers(customer_token)).json()
    assert len(loans_me["loans"]) == 1
    assert loans_me["loans"][0]["status"] == "approved"

    audit = client.get("/admin/audit-log", headers=_auth_headers(ctx["admin_token"])).json()
    override_entry = next(e for e in audit if e["action"] == "application.override")
    assert "Documentation was actually complete" in override_entry["reason"]
    assert override_entry["is_anomaly"] is False


def test_application_override_only_works_on_rejected_applications(client, engine):
    ctx = _setup_company(client, engine)
    customer_token = _signup_and_submit_profile(client, ctx, engine)
    queue = client.get("/compliance/queue", headers=_auth_headers(ctx["compliance_token"])).json()
    profile_id = queue[0]["id"]
    client.post(f"/compliance/profiles/{profile_id}/verify", json={"notes": None}, headers=_auth_headers(ctx["compliance_token"]))

    products = client.get("/loan-products", headers=_auth_headers(customer_token)).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")
    application = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": "5000.00"},
        headers=_auth_headers(customer_token),
    ).json()

    # Still pending — override only applies to already-decided applications.
    resp = client.post(
        f"/admin/applications/{application['id']}/override",
        json={"reason": "Trying to skip the officer"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 400


def test_double_override_is_a_conflict(client, engine):
    ctx = _setup_company(client, engine)
    _signup_and_submit_profile(client, ctx, engine)
    queue = client.get("/compliance/queue", headers=_auth_headers(ctx["compliance_token"])).json()
    profile_id = queue[0]["id"]
    client.post(f"/compliance/profiles/{profile_id}/verify", json={"notes": None}, headers=_auth_headers(ctx["compliance_token"]))

    first = client.post(
        f"/admin/kyc/{profile_id}/override",
        json={"new_status": "rejected", "reason": "Fraud suspected"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert first.status_code == 200

    # Same override again — profile is now rejected, not verified, so this is
    # a no-op transition rejected by the "already in that state" guard.
    second = client.post(
        f"/admin/kyc/{profile_id}/override",
        json={"new_status": "rejected", "reason": "Fraud suspected again"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert second.status_code == 400


def test_non_admin_cannot_override(client, engine):
    ctx = _setup_company(client, engine)
    _signup_and_submit_profile(client, ctx, engine)
    queue = client.get("/compliance/queue", headers=_auth_headers(ctx["compliance_token"])).json()
    profile_id = queue[0]["id"]
    client.post(f"/compliance/profiles/{profile_id}/verify", json={"notes": None}, headers=_auth_headers(ctx["compliance_token"]))

    resp = client.post(
        f"/admin/kyc/{profile_id}/override",
        json={"new_status": "rejected", "reason": "Trying to override as staff"},
        headers=_auth_headers(ctx["compliance_token"]),
    )
    assert resp.status_code == 403


def test_anomaly_guard_flags_same_admin_overriding_both_kyc_and_application_for_same_customer(client, engine):
    """CLAUDE.md §8 anomaly guard: the one-person-does-everything scenario
    separation of duties is meant to prevent."""
    ctx = _setup_company(client, engine)
    customer_token = _signup_and_submit_profile(client, ctx, engine)
    queue = client.get("/compliance/queue", headers=_auth_headers(ctx["compliance_token"])).json()
    profile_id = queue[0]["id"]
    client.post(f"/compliance/profiles/{profile_id}/verify", json={"notes": None}, headers=_auth_headers(ctx["compliance_token"]))

    products = client.get("/loan-products", headers=_auth_headers(customer_token)).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")
    application = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": "5000.00"},
        headers=_auth_headers(customer_token),
    ).json()
    client.post(
        f"/branch-manager/applications/{application['id']}/decide",
        json={"decision": "reject", "comments": "Insufficient documentation"},
        headers=_auth_headers(ctx["manager_token"]),
    )

    # First override: KYC (verified -> rejected) by the admin.
    kyc_override = client.post(
        f"/admin/kyc/{profile_id}/override",
        json={"new_status": "rejected", "reason": "Fraud suspected"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert kyc_override.status_code == 200

    # Second override: the SAME admin now also overrides the loan decision
    # for the SAME customer — this is the anomaly.
    app_override = client.post(
        f"/admin/applications/{application['id']}/override",
        json={"reason": "Actually let's approve it"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert app_override.status_code == 200

    audit = client.get("/admin/audit-log", headers=_auth_headers(ctx["admin_token"])).json()
    app_override_entry = next(e for e in audit if e["action"] == "application.override")
    assert app_override_entry["is_anomaly"] is True

    kyc_override_entry = next(e for e in audit if e["action"] == "kyc.override")
    assert kyc_override_entry["is_anomaly"] is False  # it was first — nothing to flag against yet


def test_anomaly_guard_does_not_flag_different_customers(client, engine):
    ctx = _setup_company(client, engine)
    customer_a_token = _signup_and_submit_profile(client, ctx, engine, email_slug="customerA", national_id="NATID-A")
    customer_b_token = _signup_and_submit_profile(client, ctx, engine, email_slug="customerB", national_id="NATID-B")

    queue = client.get("/compliance/queue", headers=_auth_headers(ctx["compliance_token"])).json()
    profile_a_id = next(p["id"] for p in queue if p["national_id_number"] == "NATID-A")
    profile_b_id = next(p["id"] for p in queue if p["national_id_number"] == "NATID-B")
    client.post(f"/compliance/profiles/{profile_a_id}/verify", json={"notes": None}, headers=_auth_headers(ctx["compliance_token"]))
    client.post(f"/compliance/profiles/{profile_b_id}/verify", json={"notes": None}, headers=_auth_headers(ctx["compliance_token"]))

    products = client.get("/loan-products", headers=_auth_headers(customer_b_token)).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")
    application_b = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": "5000.00"},
        headers=_auth_headers(customer_b_token),
    ).json()
    client.post(
        f"/branch-manager/applications/{application_b['id']}/decide",
        json={"decision": "reject", "comments": "Insufficient documentation"},
        headers=_auth_headers(ctx["manager_token"]),
    )

    # Override KYC for customer A...
    client.post(
        f"/admin/kyc/{profile_a_id}/override",
        json={"new_status": "rejected", "reason": "Fraud suspected"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    # ...then override the application for customer B — different applicant, not an anomaly.
    resp = client.post(
        f"/admin/applications/{application_b['id']}/override",
        json={"reason": "Reactivating for customer B"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 200

    audit = client.get("/admin/audit-log", headers=_auth_headers(ctx["admin_token"])).json()
    app_override_entry = next(e for e in audit if e["action"] == "application.override")
    assert app_override_entry["is_anomaly"] is False


def test_override_is_tenant_isolated(client, engine):
    ctx_a = _setup_company(client, engine, company_name="Company A")
    ctx_b = _setup_company(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"])
    _signup_and_submit_profile(client, ctx_b, engine)
    queue_b = client.get("/compliance/queue", headers=_auth_headers(ctx_b["compliance_token"])).json()
    profile_b_id = queue_b[0]["id"]
    client.post(f"/compliance/profiles/{profile_b_id}/verify", json={"notes": None}, headers=_auth_headers(ctx_b["compliance_token"]))

    resp = client.post(
        f"/admin/kyc/{profile_b_id}/override",
        json={"new_status": "rejected", "reason": "Cross-company attempt"},
        headers=_auth_headers(ctx_a["admin_token"]),
    )
    assert resp.status_code == 404
