"""CLAUDE.md §21: tenant profile + branding. super_admin sets everything at
creation; system_administrator may later edit only the client-facing subset
(contacts, address, logo, brand colors) via PATCH /companies/me — never
name, legal_name, registration_number, or signup_code.
"""

from tests.conftest import seed_super_admin
from tests.test_credit import _auth_headers, _login


def _create_company_with_branding(client, platform_token, **overrides):
    body = {
        "name": "Company A",
        "admin_email": "admin@companya.example.com",
        "admin_password": "admin-pass-123",
        "admin_full_name": "Admin",
        "legal_name": "Company A Financial Services Ltd",
        "registration_number": "REG-12345",
        "support_email": "support@companya.example.com",
        "support_phone": "+254700000001",
        "address": "1 Main St, Nairobi",
        "logo_url": "https://example.com/logo.png",
        "brand_primary_color": "#4F46E5",
        "brand_accent_color": "#7C3AED",
        **overrides,
    }
    return client.post("/platform/companies", json=body, headers=_auth_headers(platform_token))


def test_create_company_with_branding_fields_returns_them(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")

    resp = _create_company_with_branding(client, platform_token)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["legal_name"] == "Company A Financial Services Ltd"
    assert body["registration_number"] == "REG-12345"
    assert body["support_email"] == "support@companya.example.com"
    assert body["brand_primary_color"] == "#4F46E5"
    assert body["brand_accent_color"] == "#7C3AED"


def test_create_company_rejects_invalid_hex_color(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")

    resp = _create_company_with_branding(client, platform_token, brand_primary_color="not-a-color")
    assert resp.status_code == 422


def test_create_company_without_branding_still_works(client, engine):
    """Branding is optional polish — a company with none falls back to
    platform defaults, never a required step (CLAUDE.md §21)."""
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")

    resp = client.post(
        "/platform/companies",
        json={
            "name": "Company A",
            "admin_email": "admin@companya.example.com",
            "admin_password": "admin-pass-123",
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["brand_primary_color"] is None


def test_system_administrator_can_update_profile_subset(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company_with_branding(client, platform_token)
    admin_token = _login(client, "admin@companya.example.com", "admin-pass-123")

    resp = client.patch(
        "/companies/me",
        json={"tagline": "Fast, fair loans", "brand_primary_color": "#111111", "support_phone": "+254700000099"},
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tagline"] == "Fast, fair loans"
    assert body["brand_primary_color"] == "#111111"
    assert body["support_phone"] == "+254700000099"


def test_system_administrator_profile_update_cannot_touch_restricted_fields(client, engine):
    """name/legal_name/registration_number/signup_code are super_admin-only —
    the PATCH /companies/me schema simply has no field for them."""
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company_with_branding(client, platform_token)
    admin_token = _login(client, "admin@companya.example.com", "admin-pass-123")

    resp = client.patch(
        "/companies/me",
        json={"name": "Renamed Co", "legal_name": "Sneaky Ltd", "tagline": "ok"},
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text

    company_info = client.get("/companies/me", headers=_auth_headers(admin_token)).json()
    assert company_info["name"] == "Company A"  # unchanged

    platform_view = client.get("/platform/companies", headers=_auth_headers(platform_token)).json()
    assert platform_view[0]["legal_name"] == "Company A Financial Services Ltd"  # unchanged


def test_non_system_administrator_cannot_update_company_profile(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company_with_branding(client, platform_token)

    resp = client.patch(
        "/companies/me",
        json={"tagline": "Hijacked"},
        headers=_auth_headers(platform_token),
    )
    assert resp.status_code == 403


def test_signup_resolve_includes_branding(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company_with_branding(client, platform_token).json()

    resp = client.get(f"/signup/resolve/{company['signup_code']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["logo_url"] == "https://example.com/logo.png"
    assert body["brand_primary_color"] == "#4F46E5"
