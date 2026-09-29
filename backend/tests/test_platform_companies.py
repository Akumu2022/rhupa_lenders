from tests.conftest import seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_super_admin_creates_company_and_seeds_its_admin(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    token = _login(client, "platform@rupha.example.com", "platform-pass-1")

    resp = client.post(
        "/platform/companies",
        json={
            "name": "Acme Lending",
            "admin_email": "admin@acme.example.com",
            "admin_password": "acme-admin-pass",
            "admin_full_name": "Acme Admin",
        },
        headers=_auth_headers(token),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Acme Lending"
    assert body["status"] == "active"
    assert len(body["signup_code"]) >= 10

    login_resp = client.post(
        "/auth/login", json={"email": "admin@acme.example.com", "password": "acme-admin-pass"}
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["role"] == "system_administrator"
    assert login_resp.json()["company_id"] == body["id"]


def test_non_super_admin_cannot_create_companies(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = client.post(
        "/platform/companies",
        json={
            "name": "Acme Lending",
            "admin_email": "admin@acme.example.com",
            "admin_password": "acme-admin-pass",
            "admin_full_name": "Acme Admin",
        },
        headers=_auth_headers(token),
    ).json()

    admin_token = _login(client, "admin@acme.example.com", "acme-admin-pass")

    resp = client.post(
        "/platform/companies",
        json={
            "name": "Rogue Co",
            "admin_email": "x@rogue.example.com",
            "admin_password": "rogue-pass-123",
            "admin_full_name": "Rogue Admin",
        },
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 403
    assert company["id"]  # sanity: the legit company really was created


def test_platform_companies_list_is_cross_company_but_super_admin_only(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    token = _login(client, "platform@rupha.example.com", "platform-pass-1")

    for name in ("Company A", "Company B"):
        client.post(
            "/platform/companies",
            json={
                "name": name,
                "admin_email": f"admin@{name.lower().replace(' ', '')}.example.com",
                "admin_password": "password-123",
                "admin_full_name": "Admin",
            },
            headers=_auth_headers(token),
        )

    resp = client.get("/platform/companies", headers=_auth_headers(token))
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()}
    assert names == {"Company A", "Company B"}


def _create_company_and_admin(client, platform_token, name="Acme Lending", admin_email="admin@acme.example.com"):
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


def test_company_detail_shows_created_at_and_user_counts(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company_and_admin(client, token)

    resp = client.get(f"/platform/companies/{company['id']}", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created_at"] is not None
    # Just the seeded system_administrator so far — no customers yet.
    assert body["users"]["staff_total"] == 1
    assert body["users"]["staff_active"] == 1
    assert body["users"]["customer_total"] == 0


def test_company_detail_not_found_for_unknown_id(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    resp = client.get("/platform/companies/999999", headers=_auth_headers(token))
    assert resp.status_code == 404


def test_non_super_admin_cannot_view_company_detail(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company_and_admin(client, token)
    admin_token = _login(client, "admin@acme.example.com", "admin-pass-123")

    resp = client.get(f"/platform/companies/{company['id']}", headers=_auth_headers(admin_token))
    assert resp.status_code == 403


def test_company_users_list_includes_staff_and_customers(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company_and_admin(client, token)

    client.post(
        "/signup",
        json={
            "signup_code": company["signup_code"],
            "email": "customer@acme.example.com",
            "password": "customer-pass-1",
            "full_name": "Customer One",
        },
    )

    resp = client.get(f"/platform/companies/{company['id']}/users", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text
    roles = {row["role"] for row in resp.json()}
    assert roles == {"system_administrator", "customer"}


def test_company_activity_reflects_recent_audit_entries(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company_and_admin(client, token)  # writes a company.create platform audit row

    resp = client.get(f"/platform/companies/{company['id']}/activity", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["points"]) == 30
    assert sum(p["audit_log_count"] for p in body["points"]) >= 1
    assert body["last_activity_at"] is not None


def test_super_admin_can_reset_any_users_password(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company_and_admin(client, token)
    users = client.get(f"/platform/companies/{company['id']}/users", headers=_auth_headers(token)).json()
    admin_user_id = next(u["id"] for u in users if u["role"] == "system_administrator")

    resp = client.post(
        f"/platform/users/{admin_user_id}/reset-password",
        json={"new_password": "brand-new-pass-1", "reason": "Company forgot their admin password"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text

    old_login = client.post("/auth/login", json={"email": "admin@acme.example.com", "password": "admin-pass-123"})
    assert old_login.status_code == 401
    new_login = client.post("/auth/login", json={"email": "admin@acme.example.com", "password": "brand-new-pass-1"})
    assert new_login.status_code == 200

    audit = client.get("/admin/audit-log", headers=_auth_headers(new_login.json()["access_token"])).json()
    assert any(entry["action"] == "user.password_reset" for entry in audit)


def test_reset_password_requires_a_reason(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company_and_admin(client, token)
    users = client.get(f"/platform/companies/{company['id']}/users", headers=_auth_headers(token)).json()
    admin_user_id = users[0]["id"]

    resp = client.post(
        f"/platform/users/{admin_user_id}/reset-password",
        json={"new_password": "brand-new-pass-1", "reason": ""},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 422


def test_non_super_admin_cannot_reset_passwords_via_platform_route(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company_and_admin(client, token)
    admin_token = _login(client, "admin@acme.example.com", "admin-pass-123")
    users = client.get(f"/platform/companies/{company['id']}/users", headers=_auth_headers(token)).json()
    admin_user_id = users[0]["id"]

    resp = client.post(
        f"/platform/users/{admin_user_id}/reset-password",
        json={"new_password": "brand-new-pass-1", "reason": "trying anyway"},
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 403
