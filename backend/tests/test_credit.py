from datetime import date, timedelta
from decimal import Decimal

from sqlmodel import Session, select

from app.application_review import check_no_self_approval
from app.models import ApplicationReviewStage, AuditLog, Loan, RepaymentSchedule, ReviewDecision, ReviewStage, User
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


def _setup_company_with_branch_review_application(
    client,
    engine,
    *,
    company_name="Company A",
    platform_token=None,
    amount_requested="5000.00",
    product_name="Salary Advance",
    include_committee=False,
    include_finance=False,
):
    """Seeds a company with a branch, a credit officer + branch manager +
    cashier/finance officer in/around that branch, and a customer whose KYC
    is verified and who has one application on the Salary Advance product
    (5.00% interest, 30-day term), sitting at pending_branch_review.

    CLAUDE.md §7: self-signup never sets branch_id — that's only wired for
    credit-officer registration. This test suite is about the approval
    chain, not registration mechanics, so it takes the pragmatic shortcut
    of setting the customer's branch_id directly via the DB after signup
    rather than replaying the full multipart credit-officer registration
    flow (covered by its own tests elsewhere).
    """
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

    committee_token = None
    if include_committee:
        committee_resp = client.post(
            "/staff",
            json={
                "email": f"committee@{slug}.example.com",
                "password": "committee-pass-123",
                "full_name": "Committee One",
                "role": "loan_vetting_committee",
            },
            headers=_auth_headers(admin_token),
        )
        assert committee_resp.status_code == 201, committee_resp.text
        committee_token = _login(client, f"committee@{slug}.example.com", "committee-pass-123")

    finance_token = None
    if include_finance:
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

    with Session(engine) as session:
        with tenant_context(company["id"]):
            customer = session.exec(select(User).where(User.email == f"customer@{slug}.example.com")).first()
            customer.branch_id = branch["id"]
            session.add(customer)
            session.commit()

    _submit_profile(client, customer_token)
    queue = client.get("/compliance/queue", headers=_auth_headers(credit_token)).json()
    profile_id = queue[0]["id"]
    verify_resp = client.post(
        f"/compliance/profiles/{profile_id}/verify",
        json={"notes": None},
        headers=_auth_headers(credit_token),
    )
    assert verify_resp.status_code == 200

    products = client.get("/loan-products", headers=_auth_headers(customer_token)).json()
    product = next(p for p in products if p["name"] == product_name)

    application_resp = client.post(
        "/applications",
        json={"loan_product_id": product["id"], "amount_requested": amount_requested},
        headers=_auth_headers(customer_token),
    )
    assert application_resp.status_code == 201, application_resp.text

    return {
        "platform_token": platform_token,
        "admin_token": admin_token,
        "credit_token": credit_token,
        "manager_token": manager_token,
        "committee_token": committee_token,
        "finance_token": finance_token,
        "customer_token": customer_token,
        "company": company,
        "branch": branch,
        "application": application_resp.json(),
        "loan_product": product,
    }


def test_credit_officer_queue_shows_in_review_application(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    resp = client.get("/credit/queue", headers=_auth_headers(ctx["credit_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["amount_requested"] == "5000.00"
    assert body[0]["loan_product_name"] == "Salary Advance"
    assert body[0]["status"] == "pending_branch_review"


def test_branch_manager_queue_shows_application_with_effective_limit(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    resp = client.get("/branch-manager/queue", headers=_auth_headers(ctx["manager_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["amount_requested"] == "5000.00"
    assert body[0]["over_limit"] is False
    # DEV placeholder default (app/models/loan_product.py)
    assert Decimal(body[0]["effective_limit"]) == Decimal("100000.00")


def test_branch_manager_approve_creates_loan_and_repayment_schedule(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    application_id = ctx["application"]["id"]

    resp = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Good repayment history"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "approved"
    assert body["loan_status"] == "approved"

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loan = session.exec(select(Loan).where(Loan.application_id == application_id)).first()
            schedule = session.exec(select(RepaymentSchedule).where(RepaymentSchedule.loan_id == loan.id)).all()

    assert loan.principal == Decimal("5000.00")
    # Salary Advance is 5.00% flat: 5000 * 1.05 = 5250.00
    assert loan.total_repayable == Decimal("5250.00")
    assert loan.outstanding_balance == Decimal("5250.00")
    assert len(schedule) == 1
    assert schedule[0].due_date == date.today() + timedelta(days=30)

    queue_resp = client.get("/branch-manager/queue", headers=_auth_headers(ctx["manager_token"]))
    assert queue_resp.json() == []


def test_loan_status_distinguishes_awaiting_disbursement_from_disbursed(client, engine):
    """"approved" alone doesn't say whether a loan has actually been
    disbursed yet — loan_status must track: approved (awaiting
    disbursement, per §28) -> active (disbursed by finance)."""
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    application_id = ctx["application"]["id"]

    approval = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Good repayment history"},
        headers=_auth_headers(ctx["manager_token"]),
    ).json()
    assert approval["loan_status"] == "approved"

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loan = session.exec(select(Loan).where(Loan.application_id == application_id)).first()
            loan_id = loan.id

    # CLAUDE.md §28: disbursement moved from credit_officer to
    # cashier_finance_officer — credit_officer must now be refused.
    refused = client.post(f"/credit/loans/{loan_id}/disburse", headers=_auth_headers(ctx["credit_token"]))
    assert refused.status_code == 404  # the old credit_officer route no longer exists at all

    disburse_resp = client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert disburse_resp.status_code == 200, disburse_resp.text
    assert disburse_resp.json()["loan"]["status"] == "active"

    admin_applications = client.get("/admin/applications", headers=_auth_headers(ctx["admin_token"])).json()
    assert admin_applications[0]["loan_status"] == "active"

    # A second disbursement attempt must not be silently allowed to "succeed
    # twice" — it's rejected outright.
    second_attempt = client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert second_attempt.status_code == 409, second_attempt.text


def test_rejected_application_has_no_loan_status(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    application_id = ctx["application"]["id"]

    reject_resp = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "reject", "comments": "Insufficient income"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["loan_status"] is None


def test_branch_manager_decision_writes_audit_and_review_stage(client, engine):
    """CLAUDE.md §12/§26: every privileged decision writes both an audit row
    and an append-only ApplicationReviewStage row."""
    ctx = _setup_company_with_branch_review_application(client, engine)
    application_id = ctx["application"]["id"]

    client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Good repayment history"},
        headers=_auth_headers(ctx["manager_token"]),
    )

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            audit_entries = session.exec(select(AuditLog).where(AuditLog.action == "application.approve")).all()
            stages = session.exec(
                select(ApplicationReviewStage).where(ApplicationReviewStage.application_id == application_id)
            ).all()

    assert len(audit_entries) == 1
    assert audit_entries[0].entity_id == application_id
    assert audit_entries[0].reason == "Good repayment history"

    assert len(stages) == 1
    assert stages[0].stage == ReviewStage.branch_review
    assert stages[0].decision == ReviewDecision.approve
    assert stages[0].comments == "Good repayment history"


def test_double_decide_is_a_conflict(client, engine):
    """CLAUDE.md §14: compare-and-set — a doubled click must not create two loans."""
    ctx = _setup_company_with_branch_review_application(client, engine)
    application_id = ctx["application"]["id"]

    first = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert first.status_code == 200

    second = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Approved again"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert second.status_code == 409  # already decided — no longer awaiting branch review

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loans = session.exec(select(Loan).where(Loan.application_id == application_id)).all()

    assert len(loans) == 1


def test_reject_requires_comments(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    application_id = ctx["application"]["id"]

    resp = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "reject", "comments": ""},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert resp.status_code == 422


def test_over_limit_application_can_only_be_escalated(client, engine):
    """CLAUDE.md §26: over the effective delegated limit, only "escalate" is
    accepted — an over-limit "approve" is rejected server-side, never
    trusted from the client."""
    ctx = _setup_company_with_branch_review_application(
        client, engine, product_name="Business Loan", amount_requested="150000.00"
    )
    application_id = ctx["application"]["id"]

    queue = client.get("/branch-manager/queue", headers=_auth_headers(ctx["manager_token"])).json()
    assert queue[0]["over_limit"] is True

    approve_attempt = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Trying to approve anyway"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert approve_attempt.status_code == 400

    escalate = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "escalate", "comments": "Above my limit, recommending approval"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert escalate.status_code == 200
    assert escalate.json()["status"] == "pending_committee_review"

    # And an application within limit can't be "escalated" instead of decided.
    ctx2 = _setup_company_with_branch_review_application(
        client, engine, company_name="Company C", platform_token=ctx["platform_token"]
    )
    within_limit_escalate = client.post(
        f"/branch-manager/applications/{ctx2['application']['id']}/decide",
        json={"decision": "escalate", "comments": "Not actually needed"},
        headers=_auth_headers(ctx2["manager_token"]),
    )
    assert within_limit_escalate.status_code == 400


def test_committee_decides_escalated_application(client, engine):
    ctx = _setup_company_with_branch_review_application(
        client, engine, product_name="Business Loan", amount_requested="150000.00", include_committee=True
    )
    application_id = ctx["application"]["id"]
    client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "escalate", "comments": "Above my limit"},
        headers=_auth_headers(ctx["manager_token"]),
    )

    queue = client.get("/committee/queue", headers=_auth_headers(ctx["committee_token"])).json()
    assert len(queue) == 1
    assert queue[0]["branch_manager_comments"] == "Above my limit"

    decide = client.post(
        f"/committee/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Committee approved"},
        headers=_auth_headers(ctx["committee_token"]),
    )
    assert decide.status_code == 200
    assert decide.json()["status"] == "approved"
    assert decide.json()["loan_status"] == "approved"


def test_branch_manager_cannot_see_or_act_on_other_companys_application(client, engine):
    ctx_a = _setup_company_with_branch_review_application(client, engine, company_name="Company A")
    ctx_b = _setup_company_with_branch_review_application(
        client, engine, company_name="Company B", platform_token=ctx_a["platform_token"]
    )

    decide_resp = client.post(
        f"/branch-manager/applications/{ctx_b['application']['id']}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(ctx_a["manager_token"]),
    )
    assert decide_resp.status_code == 404

    still_pending = client.get("/branch-manager/queue", headers=_auth_headers(ctx_b["manager_token"]))
    assert len(still_pending.json()) == 1


def test_customer_and_credit_officer_cannot_decide_applications(client, engine):
    """CLAUDE.md §8: as of M13, credit_officer prepares only — deciding is
    branch_manager's/committee's job."""
    ctx = _setup_company_with_branch_review_application(client, engine)
    application_id = ctx["application"]["id"]

    for token in (ctx["customer_token"], ctx["credit_token"]):
        resp = client.post(
            f"/branch-manager/applications/{application_id}/decide",
            json={"decision": "approve", "comments": "Approved"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 403


def test_credit_officer_decisions_me_always_empty_after_m13(client, engine):
    """CLAUDE.md §9/§26: "own recent decisions" now belongs to branch_manager/
    committee, not credit_officer — this endpoint stays wired for any
    historical pre-M13 rows but never grows from new activity."""
    ctx = _setup_company_with_branch_review_application(client, engine)
    application_id = ctx["application"]["id"]

    client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "reject", "comments": "Insufficient income"},
        headers=_auth_headers(ctx["manager_token"]),
    )

    resp = client.get("/credit/decisions/me", headers=_auth_headers(ctx["credit_token"]))
    assert resp.status_code == 200
    assert resp.json() == []

    # The credit officer's own in-review queue is empty too, now that it's decided.
    queue_resp = client.get("/credit/queue", headers=_auth_headers(ctx["credit_token"]))
    assert queue_resp.json() == []


def test_system_administrator_can_view_but_not_decide(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    application_id = ctx["application"]["id"]

    view_resp = client.get(
        f"/credit/applications/{application_id}", headers=_auth_headers(ctx["admin_token"])
    )
    assert view_resp.status_code == 200

    decide_resp = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert decide_resp.status_code == 403


def test_check_no_self_approval_blocks_a_repeat_actor(engine):
    """Unit-level coverage for the no-self-approval helper itself (CLAUDE.md
    §8/§26) — the current single-role-per-user model means no two stages of
    one application can naturally be reached by the same person through the
    HTTP API today, so this proves the guard directly rather than via an
    unreachable end-to-end scenario."""
    with Session(engine) as session:
        with tenant_context(None):
            from app.models import Company

            company = Company(name="Co", signup_code="CO1234567890")
            session.add(company)
            session.commit()
            session.refresh(company)

        with tenant_context(company.id):
            from app.security import hash_password
            from app.models import LoanProduct, LoanApplication, ApplicationStatus, UserRole

            actor = User(
                email="actor@co.example.com", hashed_password=hash_password("x"), role=UserRole.branch_manager,
                full_name="Actor", company_id=company.id,
            )
            customer = User(
                email="cust@co.example.com", hashed_password=hash_password("x"), role=UserRole.customer,
                full_name="Cust", company_id=company.id,
            )
            session.add(actor)
            session.add(customer)
            session.commit()
            session.refresh(actor)
            session.refresh(customer)

            product = LoanProduct(
                company_id=company.id, name="P", min_amount=Decimal("100"), max_amount=Decimal("1000"),
                interest_rate=Decimal("5"), repayment_period_days=30,
            )
            session.add(product)
            session.commit()
            session.refresh(product)

            application = LoanApplication(
                company_id=company.id, customer_id=customer.id, loan_product_id=product.id,
                amount_requested=Decimal("500"), status=ApplicationStatus.pending_branch_review,
            )
            session.add(application)
            session.commit()
            session.refresh(application)

            # First stage by `actor` is fine.
            check_no_self_approval(session, application.id, actor.id)
            session.add(
                ApplicationReviewStage(
                    company_id=company.id, application_id=application.id, stage=ReviewStage.branch_review,
                    actor_id=actor.id, decision=ReviewDecision.escalate, comments="x",
                )
            )
            session.commit()

            # Same actor trying to act again on the same application — blocked.
            import pytest
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                check_no_self_approval(session, application.id, actor.id)
            assert exc_info.value.status_code == 403
