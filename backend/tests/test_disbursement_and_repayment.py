"""CLAUDE.md M7/§28: simulated disbursement & repayment.

Disbursement is cashier_finance_officer-only (moved from credit_officer in
M13/§28), compare-and-set (§14), writes a ledger Transaction + audit entry,
and is blocked while the company is suspended (§6: "new applications /
disbursements: stopped"). Repayment is customer-only, also compare-and-set,
and stays on the suspension allow-list (rule #10: never trap a borrower
with a debt they owe).
"""

from decimal import Decimal

from sqlmodel import Session, select

from app.models import AuditLog, Loan, Transaction, User
from app.tenancy import tenant_context
from tests.conftest import create_branch, seed_super_admin


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _submit_profile(client, token, national_id="A123456789"):
    import io

    resp = client.post(
        "/profile",
        headers=_auth_headers(token),
        data={
            "date_of_birth": "1995-05-05",
            "national_id_number": national_id,
            "phone_number": "+254700000000",
            "residential_address": "123 Main St",
            "employment_status": "employed",
            "monthly_income": "45000.00",
            "occupation": "Engineer",
        },
        files={
            "id_document": ("id-front.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg"),
            "id_document_back": ("id-back.jpg", io.BytesIO(b"fake-image-bytes-back"), "image/jpeg"),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _setup_approved_loan(client, engine, *, company_name="Company A", platform_token=None, amount="5000.00"):
    """Seeds a company, verifies a customer's KYC, and gets them an
    already-approved (not yet disbursed) Salary Advance loan."""
    if platform_token is None:
        seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
        platform_token = _login(client, "platform@rupha.example.com", "platform-pass-1")

    slug = company_name.lower().replace(" ", "")
    company = client.post(
        "/platform/companies",
        json={
            "name": company_name,
            "admin_email": f"admin@{slug}.example.com",
            "admin_password": "admin-pass-123",
            "admin_full_name": "Admin",
        },
        headers=_auth_headers(platform_token),
    ).json()
    admin_token = _login(client, f"admin@{slug}.example.com", "admin-pass-123")
    branch = create_branch(client, admin_token, code=f"{slug.upper()}-1")

    compliance_resp = client.post(
        "/staff",
        json={
            "email": f"compliance@{slug}.example.com",
            "password": "compliance-pass-1",
            "full_name": "Compliance One",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    )
    assert compliance_resp.status_code == 201, compliance_resp.text
    compliance_token = _login(client, f"compliance@{slug}.example.com", "compliance-pass-1")
    # One credit_officer (not two, as before M13) — fewer logins keeps
    # two-company tests under the /auth/login rate limit.
    credit_token = compliance_token

    manager_resp = client.post(
        "/staff",
        json={
            "email": f"manager@{slug}.example.com",
            "password": "manager-pass-123",
            "full_name": "Manager One",
            "role": "branch_manager",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    )
    assert manager_resp.status_code == 201, manager_resp.text
    manager_token = _login(client, f"manager@{slug}.example.com", "manager-pass-123")

    finance_resp = client.post(
        "/staff",
        json={
            "email": f"finance@{slug}.example.com",
            "password": "finance-pass-123",
            "full_name": "Finance One",
            "role": "cashier_finance_officer",
        },
        headers=_auth_headers(admin_token),
    )
    assert finance_resp.status_code == 201, finance_resp.text
    finance_token = _login(client, f"finance@{slug}.example.com", "finance-pass-123")

    signup_resp = client.post(
        "/signup",
        json={
            "signup_code": company["signup_code"],
            "email": f"customer@{slug}.example.com",
            "password": "customer-pass-1",
            "full_name": "Customer One",
        },
    )
    assert signup_resp.status_code == 201, signup_resp.text
    customer_token = signup_resp.json()["access_token"]

    # CLAUDE.md §7: self-signup never sets branch_id — patched directly here
    # so the application routes to branch review (this suite is about
    # disbursement/repayment, not registration mechanics).
    with Session(engine) as session:
        with tenant_context(company["id"]):
            customer = session.exec(select(User).where(User.email == f"customer@{slug}.example.com")).first()
            customer.branch_id = branch["id"]
            session.add(customer)
            session.commit()

    _submit_profile(client, customer_token)
    queue = client.get("/compliance/queue", headers=_auth_headers(compliance_token)).json()
    profile_id = queue[0]["id"]
    verify_resp = client.post(
        f"/compliance/profiles/{profile_id}/verify",
        json={"notes": None},
        headers=_auth_headers(compliance_token),
    )
    assert verify_resp.status_code == 200

    products = client.get("/loan-products", headers=_auth_headers(customer_token)).json()
    salary_advance = next(p for p in products if p["name"] == "Salary Advance")
    application = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": amount},
        headers=_auth_headers(customer_token),
    ).json()
    approval = client.post(
        f"/branch-manager/applications/{application['id']}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(manager_token),
    )
    assert approval.status_code == 200, approval.text

    with Session(engine) as session:
        with tenant_context(company["id"]):
            loan = session.exec(select(Loan).where(Loan.application_id == application["id"])).first()
            loan_id = loan.id

    return {
        "platform_token": platform_token,
        "admin_token": admin_token,
        "compliance_token": compliance_token,
        "credit_token": credit_token,
        "manager_token": manager_token,
        "finance_token": finance_token,
        "customer_token": customer_token,
        "company": company,
        "loan": {"id": loan_id},
    }


def test_pending_disbursement_queue_lists_approved_loans_and_clears_after_disbursement(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]

    queue = client.get("/finance/disbursements", headers=_auth_headers(ctx["finance_token"]))
    assert queue.status_code == 200
    assert len(queue.json()) == 1
    assert queue.json()[0]["id"] == loan_id
    assert queue.json()[0]["loan_product_name"] == "Salary Advance"

    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))

    queue_after = client.get("/finance/disbursements", headers=_auth_headers(ctx["finance_token"]))
    assert queue_after.json() == []


def test_disburse_moves_loan_to_active_and_writes_transaction_and_audit(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]

    resp = client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["loan"]["status"] == "active"
    assert body["loan"]["disbursed_at"] is not None

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            transactions = session.exec(select(Transaction).where(Transaction.type == "disbursement")).all()
            audits = session.exec(select(AuditLog).where(AuditLog.action == "loan.disburse")).all()

    assert len(transactions) == 1
    assert transactions[0].amount == Decimal("5000.00")
    assert len(audits) == 1
    assert audits[0].entity_id == loan_id


def test_double_disburse_is_a_conflict(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]

    first = client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert first.status_code == 200

    second = client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert second.status_code == 409


def test_disbursement_blocked_while_company_suspended(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]

    client.post(
        f"/platform/companies/{ctx['company']['id']}/suspend",
        json={"reason": "non-payment"},
        headers=_auth_headers(ctx["platform_token"]),
    )

    resp = client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "company_suspended"


def test_only_cashier_finance_officer_can_disburse(client, engine):
    """CLAUDE.md §28 (M14): disbursement moved to cashier_finance_officer —
    the old credit_officer route is gone entirely (404), and every other
    role (including credit_officer/branch_manager on the new route) is
    refused (403)."""
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]

    old_route = client.post(f"/credit/loans/{loan_id}/disburse", headers=_auth_headers(ctx["credit_token"]))
    assert old_route.status_code == 404

    for token in (ctx["admin_token"], ctx["customer_token"], ctx["credit_token"], ctx["manager_token"]):
        resp = client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(token))
        assert resp.status_code == 403


def test_repay_full_amount_marks_loan_repaid(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))

    resp = client.post(
        f"/loans/{loan_id}/repay",
        json={"amount": "5250.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["outstanding_balance"] == "0.00"
    assert body["status"] == "repaid"

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            transactions = session.exec(select(Transaction).where(Transaction.type == "repayment")).all()

    assert len(transactions) == 1
    assert transactions[0].amount == Decimal("5250.00")

    loans_me = client.get("/loans/me", headers=_auth_headers(ctx["customer_token"])).json()
    assert loans_me["loans"][0]["status"] == "repaid"
    assert loans_me["loans"][0]["schedule"][0]["is_paid"] is True
    assert loans_me["available_credit"] == "200000.00"


def test_repay_partial_amount_reduces_balance_and_stays_active(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))

    resp = client.post(
        f"/loans/{loan_id}/repay",
        json={"amount": "2000.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["outstanding_balance"] == "3250.00"
    assert body["status"] == "active"

    loans_me = client.get("/loans/me", headers=_auth_headers(ctx["customer_token"])).json()
    assert loans_me["loans"][0]["schedule"][0]["amount_paid"] == "2000.00"
    assert loans_me["loans"][0]["schedule"][0]["is_paid"] is False


def test_repay_more_than_outstanding_is_rejected(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))

    resp = client.post(
        f"/loans/{loan_id}/repay",
        json={"amount": "99999.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert resp.status_code == 400


def test_repay_before_disbursement_is_rejected(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]

    resp = client.post(
        f"/loans/{loan_id}/repay",
        json={"amount": "1000.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert resp.status_code == 400


def test_repay_allowed_while_company_suspended(client, engine):
    """CLAUDE.md §6/rule #10: repayment stays open for a suspended company."""
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))

    client.post(
        f"/platform/companies/{ctx['company']['id']}/suspend",
        json={"reason": "non-payment"},
        headers=_auth_headers(ctx["platform_token"]),
    )

    resp = client.post(
        f"/loans/{loan_id}/repay",
        json={"amount": "1000.00"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert resp.status_code == 200, resp.text


def test_customer_cannot_repay_another_customers_loan(client, engine):
    ctx = _setup_approved_loan(client, engine)
    loan_id = ctx["loan"]["id"]
    client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))

    other_signup = client.post(
        "/signup",
        json={
            "signup_code": ctx["company"]["signup_code"],
            "email": "other@companya.example.com",
            "password": "other-pass-123",
            "full_name": "Other Customer",
        },
    )
    assert other_signup.status_code == 201
    other_token = other_signup.json()["access_token"]

    resp = client.post(
        f"/loans/{loan_id}/repay",
        json={"amount": "1000.00"},
        headers=_auth_headers(other_token),
    )
    assert resp.status_code == 404
