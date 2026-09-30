"""Branch assignment (system_administrator), branch signup links, and
re-routing unreviewed applications once a customer gets a branch."""

from sqlmodel import Session, select

from app.models import ApplicationStatus, AuditLog, LoanApplication, User
from app.tenancy import tenant_context
from tests.conftest import create_branch, seed_super_admin
from tests.test_credit import _auth_headers, _login, _submit_profile


def _company(client, platform_token, name):
    slug = name.lower().replace(" ", "")
    company = client.post(
        "/platform/companies",
        json={"name": name, "admin_email": f"admin@{slug}.example.com", "admin_password": "admin-pass-123", "admin_full_name": "Admin"},
        headers=_auth_headers(platform_token),
    ).json()
    admin_token = _login(client, f"admin@{slug}.example.com", "admin-pass-123")
    return company, admin_token, slug


def _setup(client, engine):
    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    platform = _login(client, "platform@rupha.example.com", "platform-pass-1")
    company, admin, slug = _company(client, platform, "Company A")
    branch = create_branch(client, admin, name="Nairobi", code="NRB-01")
    return platform, company, admin, slug, branch


def _signup(client, company, email, branch_code=None):
    body = {"signup_code": company["signup_code"], "email": email, "password": "customer-pass-1", "full_name": "Cust"}
    if branch_code:
        body["branch_code"] = branch_code
    return client.post("/signup", json=body)


def _user_id(engine, company_id, email):
    with Session(engine) as session:
        with tenant_context(company_id):
            return session.exec(select(User).where(User.email == email)).one().id


def test_branch_signup_link_places_customer_in_that_branch(client, engine):
    _, company, _, _, branch = _setup(client, engine)
    info = client.get(f"/signup/resolve/{company['signup_code']}?branch=NRB-01").json()
    assert info["branch_name"] == "Nairobi"

    assert _signup(client, company, "c1@x.example.com", branch_code="NRB-01").status_code == 201
    with Session(engine) as session:
        with tenant_context(company["id"]):
            assert session.exec(select(User).where(User.email == "c1@x.example.com")).one().branch_id == branch["id"]


def test_unknown_or_other_companys_branch_code_is_rejected(client, engine):
    platform, company, _, _, _ = _setup(client, engine)
    other, other_admin, _ = _company(client, platform, "Company B")
    create_branch(client, other_admin, name="Mombasa", code="MSA-01")

    assert client.get(f"/signup/resolve/{company['signup_code']}?branch=NOPE").status_code == 400
    # MSA-01 exists, but in Company B, so it is unknown to Company A's link.
    assert _signup(client, company, "c2@x.example.com", branch_code="MSA-01").status_code == 400
    assert _signup(client, company, "c3@x.example.com").status_code == 201  # plain link still works


def test_admin_sees_and_fixes_missing_branches_with_audit(client, engine):
    _, company, admin, slug, branch = _setup(client, engine)
    _signup(client, company, "nobranch@x.example.com")
    overview = client.get("/admin/branch-assignment", headers=_auth_headers(admin)).json()
    assert [c["email"] for c in overview["customers_missing_branch"]] == ["nobranch@x.example.com"]

    user_id = _user_id(engine, company["id"], "nobranch@x.example.com")
    resp = client.patch(f"/admin/users/{user_id}/branch", json={"branch_id": branch["id"]}, headers=_auth_headers(admin))
    assert resp.status_code == 200, resp.text
    assert client.get("/admin/branch-assignment", headers=_auth_headers(admin)).json()["customers_missing_branch"] == []
    with Session(engine) as session:
        with tenant_context(company["id"]):
            entry = session.exec(select(AuditLog).where(AuditLog.action == "user.branch_change")).one()
            assert entry.entity_id == user_id


def test_branch_required_roles_cannot_be_cleared(client, engine):
    _, company, admin, slug, branch = _setup(client, engine)
    client.post(
        "/staff",
        json={"email": f"co@{slug}.example.com", "password": "credit-pass-123", "full_name": "CO", "role": "credit_officer", "branch_id": branch["id"]},
        headers=_auth_headers(admin),
    )
    officer_id = _user_id(engine, company["id"], f"co@{slug}.example.com")
    resp = client.patch(f"/admin/users/{officer_id}/branch", json={"branch_id": None}, headers=_auth_headers(admin))
    assert resp.status_code == 400


def test_cannot_assign_another_companys_user_or_branch(client, engine):
    platform, company, admin, _, branch = _setup(client, engine)
    other, other_admin, _ = _company(client, platform, "Company B")
    other_branch = create_branch(client, other_admin, name="Mombasa", code="MSA-01")
    _signup(client, other, "b@x.example.com")
    _signup(client, company, "a@x.example.com")
    b_user = _user_id(engine, other["id"], "b@x.example.com")
    a_user = _user_id(engine, company["id"], "a@x.example.com")

    assert client.patch(f"/admin/users/{b_user}/branch", json={"branch_id": branch["id"]}, headers=_auth_headers(admin)).status_code == 404
    assert client.patch(f"/admin/users/{a_user}/branch", json={"branch_id": other_branch["id"]}, headers=_auth_headers(admin)).status_code == 404


def test_assigning_branch_reroutes_unreviewed_committee_application(client, engine):
    from app.models import KYCStatus, Profile

    _, company, admin, _, branch = _setup(client, engine)
    customer = _signup(client, company, "late@x.example.com").json()["access_token"]
    _submit_profile(client, customer)
    # KYC verification itself isn't under test here; mark it verified
    # directly so the customer can apply while still branchless.

    with Session(engine) as session:
        with tenant_context(company["id"]):
            profile = session.exec(select(Profile)).one()
            profile.kyc_status = KYCStatus.verified
            session.add(profile)
            session.commit()

    products = client.get("/loan-products", headers=_auth_headers(customer)).json()
    app_resp = client.post(
        "/applications", json={"loan_product_id": products[0]["id"], "amount_requested": str(products[0]["min_amount"])}, headers=_auth_headers(customer)
    )
    assert app_resp.json()["status"] == "pending_committee_review"  # no branch -> skipped branch review

    user_id = _user_id(engine, company["id"], "late@x.example.com")
    resp = client.patch(f"/admin/users/{user_id}/branch", json={"branch_id": branch["id"]}, headers=_auth_headers(admin)).json()
    assert resp["rerouted_application_ids"] == [app_resp.json()["id"]]
    with Session(engine) as session:
        with tenant_context(company["id"]):
            application = session.get(LoanApplication, app_resp.json()["id"])
            assert application.status == ApplicationStatus.pending_branch_review
            assert application.branch_id == branch["id"]


def test_admin_can_view_signup_code_other_roles_cannot(client, engine):
    _, company, admin, slug, branch = _setup(client, engine)
    resp = client.get("/admin/signup-link", headers=_auth_headers(admin))
    assert resp.json()["signup_code"] == company["signup_code"]
    customer = _signup(client, company, "c@x.example.com").json()["access_token"]
    assert client.get("/admin/signup-link", headers=_auth_headers(customer)).status_code == 403
