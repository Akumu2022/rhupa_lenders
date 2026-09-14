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


def test_system_administrator_creates_staff_inheriting_company_id(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company(client, platform_token)
    admin_token = _login(client, "admin@a.example.com", "admin-pass-123")
    branch = create_branch(client, admin_token)

    resp = client.post(
        "/staff",
        json={
            "email": "compliance@a.example.com",
            "password": "compliance-pass-1",
            "full_name": "Compliance One",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["company_id"] == company["id"]
    assert body["role"] == "credit_officer"
    assert body["branch_id"] == branch["id"]


def test_staff_creation_ignores_company_id_in_body(client, engine):
    """CLAUDE.md §4: registration/creation never accepts company_id from the
    request body — company_id is inherited from the creating admin only."""
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company_a = _create_company(client, platform_token, "Company A", "admin@a.example.com")
    _create_company(client, platform_token, "Company B", "admin@b.example.com")
    admin_a_token = _login(client, "admin@a.example.com", "admin-pass-123")
    branch_a = create_branch(client, admin_a_token)

    resp = client.post(
        "/staff",
        json={
            "email": "sneaky@a.example.com",
            "password": "sneaky-pass-1",
            "full_name": "Sneaky",
            "role": "credit_officer",
            "branch_id": branch_a["id"],
            "company_id": 999999,  # not a real field on the schema — must be ignored
        },
        headers=_auth_headers(admin_a_token),
    )
    assert resp.status_code == 201
    assert resp.json()["company_id"] == company_a["id"]


def test_staff_creation_rejects_disallowed_roles(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company(client, platform_token)
    admin_token = _login(client, "admin@a.example.com", "admin-pass-123")

    resp = client.post(
        "/staff",
        json={
            "email": "wannabe@a.example.com",
            "password": "wannabe-pass-1",
            "full_name": "Wannabe",
            "role": "company_admin",
        },
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 422  # not one of the two allowed literals


def test_non_admin_cannot_create_staff(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company(client, platform_token)
    admin_token = _login(client, "admin@a.example.com", "admin-pass-123")
    branch = create_branch(client, admin_token)
    officer_resp = client.post(
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

    resp = client.post(
        "/staff",
        json={
            "email": "another@a.example.com",
            "password": "another-pass-1",
            "full_name": "Another",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(officer_token),
    )
    assert resp.status_code == 403
    assert officer_resp.status_code == 201


def test_list_staff_returns_only_this_companys_staff(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company(client, platform_token, "Company A", "admin@a.example.com")
    _create_company(client, platform_token, "Company B", "admin@b.example.com")
    admin_a_token = _login(client, "admin@a.example.com", "admin-pass-123")
    admin_b_token = _login(client, "admin@b.example.com", "admin-pass-123")
    branch_a = create_branch(client, admin_a_token)
    branch_b = create_branch(client, admin_b_token)

    client.post(
        "/staff",
        json={
            "email": "credit@a.example.com",
            "password": "credit-pass-1",
            "full_name": "A Credit",
            "role": "credit_officer",
            "branch_id": branch_a["id"],
        },
        headers=_auth_headers(admin_a_token),
    )
    client.post(
        "/staff",
        json={
            "email": "credit@b.example.com",
            "password": "credit-pass-1",
            "full_name": "B Credit",
            "role": "credit_officer",
            "branch_id": branch_b["id"],
        },
        headers=_auth_headers(admin_b_token),
    )

    resp = client.get("/staff", headers=_auth_headers(admin_a_token))
    assert resp.status_code == 200
    assert [s["email"] for s in resp.json()] == ["credit@a.example.com"]


def test_deactivate_staff_locks_them_out_immediately(client, engine):
    """CLAUDE.md §6/rule #15: is_active is checked on every request, not just
    when a JWT expires."""
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company(client, platform_token)
    admin_token = _login(client, "admin@a.example.com", "admin-pass-123")
    branch = create_branch(client, admin_token)

    staff = client.post(
        "/staff",
        json={
            "email": "credit@a.example.com",
            "password": "credit-pass-1",
            "full_name": "Credit One",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    ).json()
    staff_token = _login(client, "credit@a.example.com", "credit-pass-1")

    deactivate_resp = client.post(f"/staff/{staff['id']}/deactivate", headers=_auth_headers(admin_token))
    assert deactivate_resp.status_code == 200
    assert deactivate_resp.json()["is_active"] is False

    blocked = client.get("/credit/queue", headers=_auth_headers(staff_token))
    assert blocked.status_code == 403

    reactivate_resp = client.post(f"/staff/{staff['id']}/reactivate", headers=_auth_headers(admin_token))
    assert reactivate_resp.status_code == 200
    assert reactivate_resp.json()["is_active"] is True

    unblocked = client.get("/credit/queue", headers=_auth_headers(staff_token))
    assert unblocked.status_code == 200


def test_double_deactivate_is_a_conflict(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company(client, platform_token)
    admin_token = _login(client, "admin@a.example.com", "admin-pass-123")
    branch = create_branch(client, admin_token)

    staff = client.post(
        "/staff",
        json={
            "email": "credit@a.example.com",
            "password": "credit-pass-1",
            "full_name": "Credit One",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    ).json()

    first = client.post(f"/staff/{staff['id']}/deactivate", headers=_auth_headers(admin_token))
    assert first.status_code == 200
    second = client.post(f"/staff/{staff['id']}/deactivate", headers=_auth_headers(admin_token))
    assert second.status_code == 409


def test_system_administrator_cannot_deactivate_another_companys_staff(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company(client, platform_token, "Company A", "admin@a.example.com")
    _create_company(client, platform_token, "Company B", "admin@b.example.com")
    admin_a_token = _login(client, "admin@a.example.com", "admin-pass-123")
    admin_b_token = _login(client, "admin@b.example.com", "admin-pass-123")
    branch_b = create_branch(client, admin_b_token)

    staff_b = client.post(
        "/staff",
        json={
            "email": "credit@b.example.com",
            "password": "credit-pass-1",
            "full_name": "B Credit",
            "role": "credit_officer",
            "branch_id": branch_b["id"],
        },
        headers=_auth_headers(admin_b_token),
    ).json()

    resp = client.post(f"/staff/{staff_b['id']}/deactivate", headers=_auth_headers(admin_a_token))
    assert resp.status_code == 404


def test_resolve_signup_code_returns_name_and_active_status(client, engine):
    """CLAUDE.md §17: pre-validate a code before the form is filled — name
    and active status only, nothing sensitive (no id, no code echoed back)."""
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company(client, platform_token)

    resp = client.get(f"/signup/resolve/{company['signup_code']}")
    assert resp.status_code == 200
    assert resp.json() == {
        "company_name": "Company A",
        "active": True,
        "logo_url": None,
        "brand_primary_color": None,
    }


def test_resolve_signup_code_reflects_suspended_company(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company(client, platform_token)
    client.post(
        f"/platform/companies/{company['id']}/suspend",
        json={"reason": "non-payment"},
        headers=_auth_headers(platform_token),
    )

    resp = client.get(f"/signup/resolve/{company['signup_code']}")
    assert resp.status_code == 200
    assert resp.json() == {
        "company_name": "Company A",
        "active": False,
        "logo_url": None,
        "brand_primary_color": None,
    }


def test_resolve_signup_code_rejects_unknown_code(client, engine):
    resp = client.get("/signup/resolve/NOT-A-REAL-CODE")
    assert resp.status_code == 404


def test_customer_signup_with_valid_code(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company(client, platform_token)
    signup_code = client.get("/platform/companies", headers=_auth_headers(platform_token)).json()[0][
        "signup_code"
    ]

    resp = client.post(
        "/signup",
        json={
            "signup_code": signup_code,
            "email": "customer@a.example.com",
            "password": "customer-pass-1",
            "full_name": "Customer One",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "customer"
    assert body["company_id"] == company["id"]


def test_customer_signup_rejects_unknown_code(client, engine):
    resp = client.post(
        "/signup",
        json={
            "signup_code": "NOT-A-REAL-CODE",
            "email": "customer@nowhere.example.com",
            "password": "customer-pass-1",
            "full_name": "Nobody",
        },
    )
    assert resp.status_code == 400


def test_customer_signup_rejects_suspended_company(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company = _create_company(client, platform_token)
    signup_code = client.get("/platform/companies", headers=_auth_headers(platform_token)).json()[0][
        "signup_code"
    ]
    client.post(
        f"/platform/companies/{company['id']}/suspend",
        json={"reason": "non-payment"},
        headers=_auth_headers(platform_token),
    )

    resp = client.post(
        "/signup",
        json={
            "signup_code": signup_code,
            "email": "customer@a.example.com",
            "password": "customer-pass-1",
            "full_name": "Customer One",
        },
    )
    assert resp.status_code == 403


def test_customer_signup_body_cannot_pick_role_or_company_id(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")
    _create_company(client, platform_token)
    signup_code = client.get("/platform/companies", headers=_auth_headers(platform_token)).json()[0][
        "signup_code"
    ]

    resp = client.post(
        "/signup",
        json={
            "signup_code": signup_code,
            "email": "customer@a.example.com",
            "password": "customer-pass-1",
            "full_name": "Customer One",
            "role": "super_admin",
            "company_id": 999999,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "customer"
