"""CLAUDE.md §18: the top bar's "current company" label for staff/customers."""

from tests.conftest import seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_staff_sees_own_company_name_and_status(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")

    company = client.post(
        "/platform/companies",
        json={
            "name": "Company A",
            "admin_email": "admin@companya.example.com",
            "admin_password": "admin-pass-123",
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    ).json()
    admin_token = _login(client, "admin@companya.example.com", "admin-pass-123")

    resp = client.get("/companies/me", headers=_auth_headers(admin_token))
    assert resp.status_code == 200
    assert resp.json() == {
        "id": company["id"],
        "name": "Company A",
        "status": "active",
        "tagline": None,
        "logo_url": None,
        "brand_primary_color": None,
        "brand_accent_color": None,
        "support_email": None,
        "support_phone": None,
        "address": None,
    }


def test_super_admin_has_no_single_company(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")

    resp = client.get("/companies/me", headers=_auth_headers(platform_token))
    assert resp.status_code == 404


def test_cannot_reach_another_companys_info(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")

    client.post(
        "/platform/companies",
        json={
            "name": "Company A",
            "admin_email": "admin@companya.example.com",
            "admin_password": "admin-pass-123",
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    )
    company_b = client.post(
        "/platform/companies",
        json={
            "name": "Company B",
            "admin_email": "admin@companyb.example.com",
            "admin_password": "admin-pass-123",
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    ).json()

    admin_a_token = _login(client, "admin@companya.example.com", "admin-pass-123")
    resp = client.get("/companies/me", headers=_auth_headers(admin_a_token))
    assert resp.json()["id"] != company_b["id"]
    assert resp.json()["name"] == "Company A"
