"""CLAUDE.md §4: TOTP MFA for staff roles — enroll -> confirm -> login now
requires a code; wrong codes and reused recovery codes are rejected;
customers are never prompted; disable requires password + a valid code.
"""

import pyotp

from tests.conftest import seed_super_admin


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def _setup_admin(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1").json()["access_token"]

    company_resp = client.post(
        "/platform/companies",
        json={
            "name": "MFA Co",
            "admin_email": "admin@mfaco.example.com",
            "admin_password": "admin-pass-123",
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    )
    assert company_resp.status_code == 201, company_resp.text

    admin_login = _login(client, "admin@mfaco.example.com", "admin-pass-123")
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    return admin_token


def _enroll_and_confirm(client, admin_token):
    enroll_resp = client.post("/auth/mfa/enroll", headers=_auth_headers(admin_token))
    assert enroll_resp.status_code == 200, enroll_resp.text
    secret = pyotp.parse_uri(enroll_resp.json()["otpauth_uri"]).secret

    confirm_resp = client.post(
        "/auth/mfa/confirm",
        json={"code": pyotp.TOTP(secret).now()},
        headers=_auth_headers(admin_token),
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    recovery_codes = confirm_resp.json()["recovery_codes"]
    assert len(recovery_codes) == 10
    return secret, recovery_codes


def test_enroll_confirm_then_login_requires_mfa_code(client, engine):
    admin_token = _setup_admin(client, engine)

    before = client.get("/auth/mfa/status", headers=_auth_headers(admin_token))
    assert before.status_code == 200
    assert before.json()["mfa_enabled"] is False

    secret, _ = _enroll_and_confirm(client, admin_token)

    after = client.get("/auth/mfa/status", headers=_auth_headers(admin_token))
    assert after.json()["mfa_enabled"] is True

    login_resp = _login(client, "admin@mfaco.example.com", "admin-pass-123")
    assert login_resp.status_code == 200
    body = login_resp.json()
    assert body["mfa_required"] is True
    mfa_token = body["mfa_token"]

    verify_resp = client.post("/auth/mfa/verify", json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()})
    assert verify_resp.status_code == 200, verify_resp.text
    real_token = verify_resp.json()["access_token"]

    # Confirm the issued token actually works against a protected route.
    products_resp = client.get("/admin/products", headers=_auth_headers(real_token))
    assert products_resp.status_code == 200


def test_mfa_pending_token_cannot_be_used_as_a_bearer_token(client, engine):
    """The mfa_pending token proves the password step succeeded but must
    never itself grant API access — get_current_user rejects its `purpose`
    claim outright (app/security.py)."""
    admin_token = _setup_admin(client, engine)
    _enroll_and_confirm(client, admin_token)

    mfa_token = _login(client, "admin@mfaco.example.com", "admin-pass-123").json()["mfa_token"]
    resp = client.get("/admin/products", headers=_auth_headers(mfa_token))
    assert resp.status_code == 401


def test_wrong_mfa_code_is_rejected(client, engine):
    admin_token = _setup_admin(client, engine)
    _enroll_and_confirm(client, admin_token)

    mfa_token = _login(client, "admin@mfaco.example.com", "admin-pass-123").json()["mfa_token"]
    resp = client.post("/auth/mfa/verify", json={"mfa_token": mfa_token, "code": "000000"})
    assert resp.status_code == 401


def test_recovery_code_is_single_use(client, engine):
    admin_token = _setup_admin(client, engine)
    _, recovery_codes = _enroll_and_confirm(client, admin_token)
    code = recovery_codes[0]

    mfa_token = _login(client, "admin@mfaco.example.com", "admin-pass-123").json()["mfa_token"]
    first_use = client.post("/auth/mfa/verify", json={"mfa_token": mfa_token, "recovery_code": code})
    assert first_use.status_code == 200, first_use.text

    mfa_token_2 = _login(client, "admin@mfaco.example.com", "admin-pass-123").json()["mfa_token"]
    second_use = client.post("/auth/mfa/verify", json={"mfa_token": mfa_token_2, "recovery_code": code})
    assert second_use.status_code == 401


def test_customer_role_never_prompted_and_cannot_enroll(client, engine):
    seed_super_admin(engine, email="platform2@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform2@rupha.example.com", "platform-pass-1").json()["access_token"]
    company_resp = client.post(
        "/platform/companies",
        json={
            "name": "Customer Co",
            "admin_email": "admin@customerco.example.com",
            "admin_password": "admin-pass-123",
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    ).json()

    signup_resp = client.post(
        "/signup",
        json={
            "signup_code": company_resp["signup_code"],
            "email": "customer@customerco.example.com",
            "password": "customer-pass-1",
            "full_name": "Customer One",
        },
    )
    assert signup_resp.status_code == 201, signup_resp.text
    customer_token = signup_resp.json()["access_token"]

    enroll_resp = client.post("/auth/mfa/enroll", headers=_auth_headers(customer_token))
    assert enroll_resp.status_code == 403

    login_resp = _login(client, "customer@customerco.example.com", "customer-pass-1")
    assert login_resp.status_code == 200
    assert "mfa_required" not in login_resp.json()
    assert "access_token" in login_resp.json()


def test_disable_requires_password_and_code(client, engine):
    admin_token = _setup_admin(client, engine)
    secret, _ = _enroll_and_confirm(client, admin_token)

    wrong_password = client.post(
        "/auth/mfa/disable",
        json={"password": "wrong-password", "code": pyotp.TOTP(secret).now()},
        headers=_auth_headers(admin_token),
    )
    assert wrong_password.status_code == 401

    disable_resp = client.post(
        "/auth/mfa/disable",
        json={"password": "admin-pass-123", "code": pyotp.TOTP(secret).now()},
        headers=_auth_headers(admin_token),
    )
    assert disable_resp.status_code == 204

    login_resp = _login(client, "admin@mfaco.example.com", "admin-pass-123")
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()
