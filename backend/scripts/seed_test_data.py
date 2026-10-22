"""Create a clearly-marked TEST company with staff and dummy customers, so every
role's screens, the sidebar alert badges and the bank collections API can be
exercised end to end. Remove it later with scripts/remove_test_data.py.

It drives the platform's own API in-process (same rules, same audit trail as a
real session), against whatever DATABASE_URL points at. Run from backend/:

    .venv/Scripts/python scripts/seed_test_data.py

Everything is marked: company name "ZZ TEST COMPANY (delete later)" and emails
@zztest.example.com. Safe to run once; it refuses if the test company exists.
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.limiter import limiter
from app.main import app
from app.models import Company, Loan, User, UserRole
from app.security import create_access_token
from app.tenancy import tenant_context

COMPANY_NAME = "ZZ TEST COMPANY (delete later)"
DOMAIN = "zztest.example.com"
PASSWORD = "TestPass-2026!"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, email: str) -> str:
    limiter.reset()
    resp = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def main() -> None:
    with Session(engine) as session, tenant_context(None):
        if session.exec(select(Company).where(Company.name == COMPANY_NAME)).first() is not None:
            print("Test company already exists; run scripts/remove_test_data.py first.", file=sys.stderr)
            raise SystemExit(1)
        owner = session.exec(select(User).where(User.role == UserRole.super_admin).order_by(User.id)).first()
        if owner is None:
            print("No super_admin found in this database.", file=sys.stderr)
            raise SystemExit(1)
        platform_token = create_access_token(user_id=owner.id, role=owner.role.value, company_id=None)

    client = TestClient(app)

    company = client.post(
        "/platform/companies",
        json={
            "name": COMPANY_NAME,
            "admin_email": f"admin@{DOMAIN}",
            "admin_password": PASSWORD,
            "admin_full_name": "Test Admin",
        },
        headers=auth(platform_token),
    )
    assert company.status_code == 201, company.text
    company = company.json()
    admin_token = login(client, f"admin@{DOMAIN}")

    branch = client.post("/admin/branches", json={"name": "Test Branch", "code": "TEST-1"}, headers=auth(admin_token))
    assert branch.status_code == 201, branch.text
    branch = branch.json()

    staff = [
        ("credit", "Test Credit Officer", "credit_officer", branch["id"]),
        ("manager", "Test Branch Manager", "branch_manager", branch["id"]),
        ("committee", "Test Committee Member", "loan_vetting_committee", None),
        ("finance", "Test Finance Officer", "cashier_finance_officer", None),
        ("management", "Test Management", "management", None),
    ]
    for key, full_name, role, branch_id in staff:
        body = {"email": f"{key}@{DOMAIN}", "password": PASSWORD, "full_name": full_name, "role": role}
        if branch_id:
            body["branch_id"] = branch_id
        resp = client.post("/staff", json=body, headers=auth(admin_token))
        assert resp.status_code == 201, resp.text
    credit = login(client, f"credit@{DOMAIN}")
    manager = login(client, f"manager@{DOMAIN}")
    finance = login(client, f"finance@{DOMAIN}")

    def signup(n: int, name: str) -> str:
        limiter.reset()
        resp = client.post(
            "/signup",
            json={"signup_code": company["signup_code"], "email": f"customer{n}@{DOMAIN}", "password": PASSWORD, "full_name": name},
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["access_token"]

    def submit_profile(token: str, n: int) -> None:
        resp = client.post(
            "/profile",
            headers=auth(token),
            data={
                "date_of_birth": "1995-05-05",
                "national_id_number": f"TEST{n:06d}",
                "phone_number": f"+2547000000{n:02d}",
                "residential_address": "1 Test Street",
                "employment_status": "employed",
                "monthly_income": "45000.00",
                "occupation": "Tester",
            },
            files={
                "id_document": ("id-front.jpg", io.BytesIO(b"test-image"), "image/jpeg"),
                "id_document_back": ("id-back.jpg", io.BytesIO(b"test-image-back"), "image/jpeg"),
            },
        )
        assert resp.status_code == 201, resp.text

    def put_in_branch(n: int) -> None:
        with Session(engine) as session, tenant_context(company["id"]):
            customer = session.exec(select(User).where(User.email == f"customer{n}@{DOMAIN}")).first()
            customer.branch_id = branch["id"]
            session.add(customer)
            session.commit()

    def apply(token: str) -> dict:
        products = client.get("/loan-products", headers=auth(token)).json()
        product = next(p for p in products if p["name"] == "Salary Advance")
        resp = client.post(
            "/applications", json={"loan_product_id": product["id"], "amount_requested": "5000.00"}, headers=auth(token)
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    def approve(application_id: int) -> None:
        resp = client.post(
            f"/branch-manager/applications/{application_id}/decide",
            json={"decision": "approve", "comments": "Test approval"},
            headers=auth(manager),
        )
        assert resp.status_code == 200, resp.text

    def loan_id_for(n: int) -> int:
        with Session(engine) as session, tenant_context(company["id"]):
            customer = session.exec(select(User).where(User.email == f"customer{n}@{DOMAIN}")).first()
            return session.exec(select(Loan).where(Loan.customer_id == customer.id)).first().id

    # 1: verified, loan disbursed and active -> use for bank payment tests.
    # 2: verified, application waiting on the branch manager (manager badge).
    # 3: loan approved, waiting for disbursement (finance badge).
    # 4: profile submitted, KYC pending (credit officer badge).
    tokens = {n: signup(n, f"Test Customer {n}") for n in (1, 2, 3, 4)}
    for n in (1, 2, 3, 4):
        put_in_branch(n)
        submit_profile(tokens[n], n)
    # Verify customers 1-3 only; customer 4 stays pending on purpose.
    queue = client.get("/compliance/queue", headers=auth(credit)).json()
    for profile in queue:
        if not profile["customer_email"].startswith("customer4@"):
            resp = client.post(f"/compliance/profiles/{profile['id']}/verify", json={"notes": None}, headers=auth(credit))
            assert resp.status_code == 200, resp.text

    app1 = apply(tokens[1])
    approve(app1["id"])
    disburse = client.post(f"/finance/loans/{loan_id_for(1)}/disburse", headers=auth(finance))
    assert disburse.status_code == 200, disburse.text

    apply(tokens[2])

    app3 = apply(tokens[3])
    approve(app3["id"])

    with Session(engine) as session, tenant_context(company["id"]):
        from app.models import Profile

        numbers = {
            u.email: p.customer_number
            for p, u in session.exec(select(Profile, User).join(User, User.id == Profile.user_id)).all()
        }

    print(f"Test company id {company['id']} created. Password for every account: {PASSWORD}")
    print(f"Signup code: {company['signup_code']}")
    print("Staff: " + ", ".join(f"{k}@{DOMAIN}" for k, *_ in staff) + f", admin@{DOMAIN}")
    for n, note in {
        1: "active loan (use for bank payment tests)",
        2: "application waiting on branch manager",
        3: "approved, waiting for disbursement",
        4: "KYC pending",
    }.items():
        email = f"customer{n}@{DOMAIN}"
        print(f"  {email}  {numbers.get(email)}  {note}")


if __name__ == "__main__":
    main()
