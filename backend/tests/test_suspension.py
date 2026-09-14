from tests.conftest import create_branch, seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_company(client, platform_token, name, admin_email, admin_password="admin-pass-123"):
    resp = client.post(
        "/platform/companies",
        json={
            "name": name,
            "admin_email": admin_email,
            "admin_password": admin_password,
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_suspending_company_blocks_its_staff_but_not_another_companys(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")

    company_a = _create_company(client, platform_token, "Company A", "admin@a.example.com")
    company_b = _create_company(client, platform_token, "Company B", "admin@b.example.com")

    admin_a_token = _login(client, "admin@a.example.com", "admin-pass-123")
    admin_b_token = _login(client, "admin@b.example.com", "admin-pass-123")
    # Branches created before suspension — /admin/branches isn't on the
    # suspension allow-list either, so a suspended admin couldn't create one.
    branch_a = create_branch(client, admin_a_token, code="A-1")
    branch_b = create_branch(client, admin_b_token, code="B-1")

    suspend_resp = client.post(
        f"/platform/companies/{company_a['id']}/suspend",
        json={"reason": "non-payment"},
        headers=_auth_headers(platform_token),
    )
    assert suspend_resp.status_code == 200
    assert suspend_resp.json()["status"] == "suspended"

    blocked = client.post(
        "/staff",
        json={
            "email": "new@a.example.com",
            "password": "new-pass-123",
            "full_name": "New Staff",
            "role": "credit_officer",
            "branch_id": branch_a["id"],
        },
        headers=_auth_headers(admin_a_token),
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "company_suspended"

    unaffected = client.post(
        "/staff",
        json={
            "email": "new@b.example.com",
            "password": "new-pass-123",
            "full_name": "New Staff",
            "role": "credit_officer",
            "branch_id": branch_b["id"],
        },
        headers=_auth_headers(admin_b_token),
    )
    assert unaffected.status_code == 201


def test_reactivating_company_restores_access(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company(client, platform_token, "Company A", "admin@a.example.com")
    admin_token = _login(client, "admin@a.example.com", "admin-pass-123")
    branch = create_branch(client, admin_token)

    client.post(
        f"/platform/companies/{company['id']}/suspend",
        json={"reason": "non-payment"},
        headers=_auth_headers(platform_token),
    )
    reactivate = client.post(
        f"/platform/companies/{company['id']}/reactivate",
        json={"reason": "payment received"},
        headers=_auth_headers(platform_token),
    )
    assert reactivate.status_code == 200
    assert reactivate.json()["status"] == "active"

    resp = client.post(
        "/staff",
        json={
            "email": "new@a.example.com",
            "password": "new-pass-123",
            "full_name": "New Staff",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 201


def test_suspending_an_already_suspended_company_is_a_conflict(client, engine):
    """CLAUDE.md §14: compare-and-set — a double click/retry must not succeed
    twice or silently no-op; it must surface as 409."""
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company(client, platform_token, "Company A", "admin@a.example.com")

    first = client.post(
        f"/platform/companies/{company['id']}/suspend",
        json={"reason": "non-payment"},
        headers=_auth_headers(platform_token),
    )
    assert first.status_code == 200

    second = client.post(
        f"/platform/companies/{company['id']}/suspend",
        json={"reason": "non-payment again"},
        headers=_auth_headers(platform_token),
    )
    assert second.status_code == 409


def test_super_admin_is_exempt_from_suspension(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company(client, platform_token, "Company A", "admin@a.example.com")

    client.post(
        f"/platform/companies/{company['id']}/suspend",
        json={"reason": "non-payment"},
        headers=_auth_headers(platform_token),
    )

    resp = client.get("/platform/companies", headers=_auth_headers(platform_token))
    assert resp.status_code == 200
