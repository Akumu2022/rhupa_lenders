"""Daily end-of-day run (POST /internal/end-of-day) and the immediate
overdue -> active refresh after a payment."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from app.config import settings
from app.models import AuditLog, Loan, LoanStatus, RepaymentSchedule
from app.tenancy import tenant_context
from app.time_utils import business_today
from tests.test_credit import _auth_headers, _setup_company_with_branch_review_application
from tests.test_finance import _approve_and_disburse

SECRET = "test-cron-secret"


@pytest.fixture()
def cron_secret(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", SECRET)


def _make_overdue(engine, company_id, loan_id, days):
    with Session(engine) as session:
        with tenant_context(company_id):
            inst = session.exec(select(RepaymentSchedule).where(RepaymentSchedule.loan_id == loan_id)).first()
            inst.due_date = business_today() - timedelta(days=days)
            session.add(inst)
            session.commit()


def test_endpoint_disabled_without_configured_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "")
    assert client.post("/internal/end-of-day", headers={"X-Cron-Secret": "anything"}).status_code == 404


def test_wrong_or_missing_secret_is_rejected(client, cron_secret):
    assert client.post("/internal/end-of-day").status_code == 401
    assert client.post("/internal/end-of-day", headers={"X-Cron-Secret": "nope"}).status_code == 401


def test_end_of_day_marks_overdue_and_accrues_penalties_for_every_company(client, engine, cron_secret):
    a = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    b = _setup_company_with_branch_review_application(
        client, engine, company_name="Company B", platform_token=a["platform_token"], include_finance=True
    )
    a_loan = _approve_and_disburse(client, engine, a)
    b_loan = _approve_and_disburse(client, engine, b)
    _make_overdue(engine, a["company"]["id"], a_loan, days=6)
    _make_overdue(engine, b["company"]["id"], b_loan, days=6)

    # Nobody opens a screen: only the scheduled run touches these loans.
    resp = client.post("/internal/end-of-day", headers={"X-Cron-Secret": SECRET})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["companies"] == 2
    assert body["newly_overdue"] == 2
    assert Decimal(body["penalty_total"]) > 0

    for ctx, loan_id in ((a, a_loan), (b, b_loan)):
        with Session(engine) as session:
            with tenant_context(ctx["company"]["id"]):
                loan = session.get(Loan, loan_id)
                assert loan.status == LoanStatus.overdue
                assert loan.penalties_accrued > 0
                runs = session.exec(select(AuditLog).where(AuditLog.action == "system.end_of_day")).all()
                assert len(runs) == 1 and runs[0].actor_email == "system@platform"

    # Running again the same day applies no further penalties.
    again = client.post("/internal/end-of-day", headers={"X-Cron-Secret": SECRET}).json()
    assert Decimal(again["penalty_total"]) == 0


def test_payment_clearing_past_due_brings_loan_back_to_active_immediately(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)
    # Split the single instalment into one past due (within grace, so no
    # penalty) and one not yet due.
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            inst = session.exec(select(RepaymentSchedule).where(RepaymentSchedule.loan_id == loan_id)).one()
            half_due, half_interest = inst.amount_due / 2, inst.interest_component / 2
            inst.amount_due, inst.interest_component = half_due, half_interest
            inst.principal_component = half_due - half_interest
            inst.due_date = business_today() - timedelta(days=1)
            session.add(inst)
            session.add(
                RepaymentSchedule(
                    loan_id=loan_id, company_id=ctx["company"]["id"], installment_number=2,
                    due_date=business_today() + timedelta(days=14), amount_due=half_due,
                    principal_component=half_due - half_interest, interest_component=half_interest,
                )
            )
            session.commit()

    client.get("/analytics/dashboard", headers=_auth_headers(ctx["finance_token"]))  # sync -> overdue
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            assert session.get(Loan, loan_id).status == LoanStatus.overdue

    resp = client.post(
        f"/loans/{loan_id}/payments", json={"amount": str(half_due), "method": "cash"}, headers=_auth_headers(ctx["finance_token"])
    )
    assert resp.status_code == 201, resp.text
    # Past-due instalment cleared, next one not yet due: active right away.
    assert resp.json()["loan_status"] == "active"
