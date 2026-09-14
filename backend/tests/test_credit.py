from datetime import date, timedelta
from decimal import Decimal

from sqlmodel import Session, select

from app.models import AuditLog, Loan, RepaymentSchedule
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


def _setup_company_with_pending_application(
    client, engine, *, company_name="Company A", platform_token=None, amount_requested="5000.00"
):
    """Seeds a company with a credit officer and a customer whose KYC is
    verified and who has one pending application on the Salary Advance
    product (5.00% interest, 30-day term)."""
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

    credit_resp = client.post(
        "/staff",
        json={
            "email": f"credit@{slug}.example.com",
            "password": "credit-pass-123",
            "full_name": "Credit One",
            "role": "credit_officer",
            "branch_id": branch["id"],
        },
        headers=_auth_headers(admin_token),
    )
    assert credit_resp.status_code == 201, credit_resp.text
    credit_token = _login(client, f"credit@{slug}.example.com", "credit-pass-123")

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

    application_resp = client.post(
        "/applications",
        json={"loan_product_id": salary_advance["id"], "amount_requested": amount_requested},
        headers=_auth_headers(customer_token),
    )
    assert application_resp.status_code == 201, application_resp.text

    return {
        "platform_token": platform_token,
        "admin_token": admin_token,
        "compliance_token": compliance_token,
        "credit_token": credit_token,
        "customer_token": customer_token,
        "company": company,
        "application": application_resp.json(),
        "loan_product": salary_advance,
    }


def test_queue_shows_pending_application(client, engine):
    ctx = _setup_company_with_pending_application(client, engine)
    resp = client.get("/credit/queue", headers=_auth_headers(ctx["credit_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["amount_requested"] == "5000.00"
    assert body[0]["loan_product_name"] == "Salary Advance"
    assert body[0]["status"] == "pending"


def test_approve_creates_loan_and_repayment_schedule_with_decimal_amounts(client, engine):
    ctx = _setup_company_with_pending_application(client, engine)
    application_id = ctx["application"]["id"]

    resp = client.post(
        f"/credit/applications/{application_id}/approve",
        json={"notes": "Good repayment history"},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["application"]["status"] == "approved"
    assert body["loan"]["principal"] == "5000.00"
    # Salary Advance is 5.00% flat: 5000 * 1.05 = 5250.00
    assert body["loan"]["total_repayable"] == "5250.00"
    assert body["loan"]["outstanding_balance"] == "5250.00"
    assert body["loan"]["status"] == "approved"
    assert body["repayment_amount_due"] == "5250.00"
    assert body["repayment_due_date"] == str(date.today() + timedelta(days=30))

    queue_resp = client.get("/credit/queue", headers=_auth_headers(ctx["credit_token"]))
    assert queue_resp.json() == []


def test_loan_status_field_distinguishes_awaiting_disbursement_from_disbursed(client, engine):
    """A recurring point of confusion: "approved" alone doesn't say whether a
    loan has actually been disbursed yet. loan_status on the application
    response must track the real lifecycle: pending -> approved (awaiting
    disbursement) -> active (disbursed), and stay None for a rejection."""
    ctx = _setup_company_with_pending_application(client, engine)
    application_id = ctx["application"]["id"]

    queue = client.get("/credit/queue", headers=_auth_headers(ctx["credit_token"])).json()
    assert queue[0]["loan_status"] is None

    approval = client.post(
        f"/credit/applications/{application_id}/approve",
        json={"notes": "Good repayment history"},
        headers=_auth_headers(ctx["credit_token"]),
    ).json()
    assert approval["application"]["loan_status"] == "approved"
    loan_id = approval["loan"]["id"]

    decisions = client.get("/credit/decisions/me", headers=_auth_headers(ctx["credit_token"])).json()
    assert decisions[0]["loan_status"] == "approved"

    disburse_resp = client.post(f"/credit/loans/{loan_id}/disburse", headers=_auth_headers(ctx["credit_token"]))
    assert disburse_resp.status_code == 200, disburse_resp.text

    decisions = client.get("/credit/decisions/me", headers=_auth_headers(ctx["credit_token"])).json()
    assert decisions[0]["loan_status"] == "active"

    admin_applications = client.get("/admin/applications", headers=_auth_headers(ctx["admin_token"])).json()
    assert admin_applications[0]["loan_status"] == "active"

    # A second disbursement attempt must not be silently allowed to "succeed
    # twice" — it's rejected outright, and the ledger stays at one loan_status.
    second_attempt = client.post(f"/credit/loans/{loan_id}/disburse", headers=_auth_headers(ctx["credit_token"]))
    assert second_attempt.status_code == 409, second_attempt.text
    decisions = client.get("/credit/decisions/me", headers=_auth_headers(ctx["credit_token"])).json()
    assert decisions[0]["loan_status"] == "active"


def test_rejected_application_has_no_loan_status(client, engine):
    ctx = _setup_company_with_pending_application(client, engine)
    application_id = ctx["application"]["id"]

    reject_resp = client.post(
        f"/credit/applications/{application_id}/reject",
        json={"notes": "Insufficient income"},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert reject_resp.json()["loan_status"] is None


def test_approve_writes_audit_entry(client, engine):
    """CLAUDE.md §12: every privileged decision writes an audit row."""
    ctx = _setup_company_with_pending_application(client, engine)
    application_id = ctx["application"]["id"]

    client.post(
        f"/credit/applications/{application_id}/approve",
        json={"notes": "Good repayment history"},
        headers=_auth_headers(ctx["credit_token"]),
    )

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            entries = session.exec(
                select(AuditLog).where(AuditLog.action == "application.approve")
            ).all()

    assert len(entries) == 1
    assert entries[0].entity_id == application_id
    assert entries[0].reason == "Good repayment history"


def test_double_approve_is_a_conflict(client, engine):
    """CLAUDE.md §14: compare-and-set — a doubled click must not create two loans."""
    ctx = _setup_company_with_pending_application(client, engine)
    application_id = ctx["application"]["id"]

    first = client.post(
        f"/credit/applications/{application_id}/approve",
        json={"notes": "Approved"},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert first.status_code == 200

    second = client.post(
        f"/credit/applications/{application_id}/approve",
        json={"notes": "Approved again"},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert second.status_code == 409

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loans = session.exec(select(Loan).where(Loan.application_id == application_id)).all()
            schedules = session.exec(
                select(RepaymentSchedule).where(RepaymentSchedule.loan_id == loans[0].id)
            ).all()

    assert len(loans) == 1
    assert len(schedules) == 1


def test_reject_requires_notes(client, engine):
    ctx = _setup_company_with_pending_application(client, engine)
    application_id = ctx["application"]["id"]

    resp = client.post(
        f"/credit/applications/{application_id}/reject",
        json={"notes": ""},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert resp.status_code == 422


def test_reject_marks_application_rejected_and_writes_audit(client, engine):
    ctx = _setup_company_with_pending_application(client, engine)
    application_id = ctx["application"]["id"]

    resp = client.post(
        f"/credit/applications/{application_id}/reject",
        json={"notes": "Insufficient income"},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["review_notes"] == "Insufficient income"

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            entries = session.exec(
                select(AuditLog).where(AuditLog.action == "application.reject")
            ).all()

    assert len(entries) == 1
    assert entries[0].reason == "Insufficient income"


def test_credit_officer_cannot_see_or_act_on_other_companys_application(client, engine):
    ctx_a = _setup_company_with_pending_application(client, engine, company_name="Company A")
    ctx_b = _setup_company_with_pending_application(
        client, engine, company_name="Company B", platform_token=ctx_a["platform_token"]
    )

    resp = client.get(
        f"/credit/applications/{ctx_b['application']['id']}",
        headers=_auth_headers(ctx_a["credit_token"]),
    )
    assert resp.status_code == 404

    approve_resp = client.post(
        f"/credit/applications/{ctx_b['application']['id']}/approve",
        json={"notes": "Approved"},
        headers=_auth_headers(ctx_a["credit_token"]),
    )
    assert approve_resp.status_code == 404

    # Company B's own application is untouched and still visible to its own officer.
    still_pending = client.get("/credit/queue", headers=_auth_headers(ctx_b["credit_token"]))
    assert len(still_pending.json()) == 1


def test_customer_cannot_approve_or_reject(client, engine):
    """CLAUDE.md §8: as of M10 (§3), KYC and loan-decision duties both sit
    under `credit_officer` (compliance_officer retired) — a credit_officer
    legitimately may approve. The separation-of-duties chain that keeps
    preparation and decision apart (credit_officer prepares, branch_manager/
    committee decide) ships in M13; only a customer is rejected here today."""
    ctx = _setup_company_with_pending_application(client, engine)
    application_id = ctx["application"]["id"]

    resp = client.post(
        f"/credit/applications/{application_id}/approve",
        json={"notes": "Approved"},
        headers=_auth_headers(ctx["customer_token"]),
    )
    assert resp.status_code == 403


def test_decisions_me_lists_only_this_officers_past_decisions(client, engine):
    """CLAUDE.md §9: credit officer's "own recent decisions"."""
    ctx = _setup_company_with_pending_application(client, engine)
    application_id = ctx["application"]["id"]

    empty = client.get("/credit/decisions/me", headers=_auth_headers(ctx["credit_token"]))
    assert empty.status_code == 200
    assert empty.json() == []

    client.post(
        f"/credit/applications/{application_id}/reject",
        json={"notes": "Insufficient income"},
        headers=_auth_headers(ctx["credit_token"]),
    )

    resp = client.get("/credit/decisions/me", headers=_auth_headers(ctx["credit_token"]))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == application_id
    assert resp.json()[0]["status"] == "rejected"

    # A pending application (never decided) never shows up here.
    queue_resp = client.get("/credit/queue", headers=_auth_headers(ctx["credit_token"]))
    assert queue_resp.json() == []


def test_system_administrator_can_view_but_not_act(client, engine):
    ctx = _setup_company_with_pending_application(client, engine)
    application_id = ctx["application"]["id"]

    view_resp = client.get(
        f"/credit/applications/{application_id}", headers=_auth_headers(ctx["admin_token"])
    )
    assert view_resp.status_code == 200

    approve_resp = client.post(
        f"/credit/applications/{application_id}/approve",
        json={"notes": "Approved"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert approve_resp.status_code == 403
