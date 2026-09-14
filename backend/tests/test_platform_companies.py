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
