"""CLAUDE.md §9/M8: system_administrator's own audit log — read-only, tenant-scoped,
and includes platform actions targeting their company (e.g. a suspension)
alongside their own staff's decisions."""

from tests.conftest import create_branch, seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_company(client, platform_token, name="Company A", admin_email="admin@a.example.com"):
    resp = client.post(
        "/platform/companies",
        json={
            "name": name,
            "admin_email": admin_email,
            "admin_password": "admin-pass-123",
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_audit_log_shows_staff_actions_and_platform_actions_on_own_company(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company(client, platform_token)
    admin_token = _login(client, "admin@a.example.com", "admin-pass-123")
    branch = create_branch(client, admin_token)

    client.post(
        "/staff",
        json={
            "email": "credit@a.example.com",
            "password": "credit-pass-1",
            "full_name": "Credit One",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    )
    client.post(
        f"/platform/companies/{company['id']}/suspend",
        json={"reason": "non-payment"},
        headers=_auth_headers(platform_token),
    )
    client.post(
        f"/platform/companies/{company['id']}/reactivate",
        json={"reason": "payment received"},
        headers=_auth_headers(platform_token),
    )

    resp = client.get("/admin/audit-log", headers=_auth_headers(admin_token))
    assert resp.status_code == 200
    actions = [entry["action"] for entry in resp.json()]
    assert "staff.create" in actions
    assert "company.suspend" in actions
    assert "company.reactivate" in actions

    reactivate_entry = next(e for e in resp.json() if e["action"] == "company.reactivate")
    assert reactivate_entry["reason"] == "payment received"
    assert reactivate_entry["is_platform_action"] is True


def test_audit_log_is_tenant_isolated(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company(client, platform_token, "Company A", "admin@a.example.com")
    company_b = _create_company(client, platform_token, "Company B", "admin@b.example.com")
    admin_a_token = _login(client, "admin@a.example.com", "admin-pass-123")

    client.post(
        f"/platform/companies/{company_b['id']}/suspend",
        json={"reason": "non-payment"},
        headers=_auth_headers(platform_token),
    )

    resp = client.get("/admin/audit-log", headers=_auth_headers(admin_a_token))
    assert resp.status_code == 200
    assert all(e["entity_id"] != company_b["id"] or e["action"] != "company.suspend" for e in resp.json())


def test_non_admin_cannot_view_audit_log(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company(client, platform_token)
    admin_token = _login(client, "admin@a.example.com", "admin-pass-123")
    branch = create_branch(client, admin_token)
    client.post(
        "/staff",
        json={
            "email": "credit@a.example.com",
            "password": "credit-pass-1",
            "full_name": "Credit One",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    )
    officer_token = _login(client, "credit@a.example.com", "credit-pass-1")

    resp = client.get("/admin/audit-log", headers=_auth_headers(officer_token))
    assert resp.status_code == 403
