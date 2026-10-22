"""Payment automation: per-company settings, automatic disbursement after a final
approval, and due-date STK-push reminders. Everything runs on the simulated
gateway (CLAUDE.md §1); a failing gateway is injected where failure matters."""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app import disbursement
from app.models import AuditAction, AuditLog, Company, CompanyStatus, Loan, LoanStatus, RepaymentSchedule, Transaction
from app.payment_gateway import GatewayResult
from app.stk_reminders import run_stk_reminders
from app.tenancy import tenant_context
from app.time_utils import business_today
from tests.test_credit import _auth_headers, _setup_company_with_branch_review_application

NAIROBI = ZoneInfo("Africa/Nairobi")


def _settings(client, ctx, **body):
    return client.patch("/companies/me/payment-settings", json=body, headers=_auth_headers(ctx["admin_token"]))


def _approve(client, ctx):
    resp = client.post(
        f"/branch-manager/applications/{ctx['application']['id']}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert resp.status_code == 200, resp.text


def _loan(engine, ctx) -> Loan:
    with Session(engine) as session, tenant_context(ctx["company"]["id"]):
        return session.exec(select(Loan)).first()


def _audit_actions(engine, ctx) -> list[str]:
    with Session(engine) as session, tenant_context(ctx["company"]["id"]):
        return [a.action for a in session.exec(select(AuditLog).order_by(AuditLog.id)).all()]


class FailingGateway:
    def send_money(self, **_):
        return GatewayResult(ok=False, reference=None, message="provider unavailable")

    def request_payment(self, **_):
        return GatewayResult(ok=False, reference=None, message="provider unavailable")


# --- settings ---------------------------------------------------------------


def test_settings_default_off_and_admin_only(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    got = client.get("/companies/me/payment-settings", headers=_auth_headers(ctx["admin_token"])).json()
    assert got == {"auto_disburse_enabled": False, "auto_disburse_max_amount": None, "stk_push_enabled": False}

    for token in (ctx["manager_token"], ctx["finance_token"], ctx["customer_token"]):
        assert client.get("/companies/me/payment-settings", headers=_auth_headers(token)).status_code == 403
        denied = client.patch(
            "/companies/me/payment-settings", json={"stk_push_enabled": True}, headers=_auth_headers(token)
        )
        assert denied.status_code == 403


def test_auto_disburse_needs_a_maximum_and_changes_are_audited(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    assert _settings(client, ctx, auto_disburse_enabled=True).status_code == 422
    assert _settings(client, ctx, auto_disburse_max_amount="0").status_code == 422

    ok = _settings(client, ctx, auto_disburse_enabled=True, auto_disburse_max_amount="10000.00")
    assert ok.status_code == 200, ok.text
    assert ok.json()["auto_disburse_enabled"] is True
    assert AuditAction.COMPANY_UPDATE_PAYMENT_SETTINGS.value in _audit_actions(engine, ctx)


# --- automatic disbursement --------------------------------------------------


def test_off_by_default_loan_waits_for_finance(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _approve(client, ctx)
    assert _loan(engine, ctx).status == LoanStatus.approved


def test_auto_disburse_releases_loan_within_limit(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _settings(client, ctx, auto_disburse_enabled=True, auto_disburse_max_amount="5000.00")  # loan is exactly 5000
    _approve(client, ctx)

    loan = _loan(engine, ctx)
    assert loan.status == LoanStatus.active and loan.disbursed_at is not None
    with Session(engine) as session, tenant_context(ctx["company"]["id"]):
        rows = session.exec(select(Transaction).where(Transaction.loan_id == loan.id)).all()
    assert [(t.type.value, t.amount) for t in rows] == [("disbursement", Decimal("5000.00"))]
    assert AuditAction.LOAN_AUTO_DISBURSE.value in _audit_actions(engine, ctx)
    # Nothing left for finance to do.
    assert client.get("/nav-badges", headers=_auth_headers(ctx["finance_token"])).json().get("/finance/disbursements") is None
    # And finance cannot disburse it a second time.
    again = client.post(f"/finance/loans/{loan.id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert again.status_code == 409


def test_loan_above_limit_still_waits_for_finance(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _settings(client, ctx, auto_disburse_enabled=True, auto_disburse_max_amount="4999.99")
    _approve(client, ctx)
    assert _loan(engine, ctx).status == LoanStatus.approved
    assert AuditAction.LOAN_AUTO_DISBURSE.value not in _audit_actions(engine, ctx)


def test_gateway_failure_leaves_loan_approved_and_is_audited(client, engine, monkeypatch):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _settings(client, ctx, auto_disburse_enabled=True, auto_disburse_max_amount="10000.00")
    monkeypatch.setattr(disbursement, "get_gateway", lambda: FailingGateway())
    _approve(client, ctx)  # the approval itself still succeeds (asserted inside)

    loan = _loan(engine, ctx)
    assert loan.status == LoanStatus.approved
    with Session(engine) as session, tenant_context(ctx["company"]["id"]):
        assert session.exec(select(Transaction).where(Transaction.loan_id == loan.id)).first() is None
        failure = session.exec(
            select(AuditLog).where(AuditLog.action == AuditAction.LOAN_AUTO_DISBURSE_FAILED.value)
        ).first()
    assert failure is not None and "provider unavailable" in failure.reason

    # Finance can still release it by hand once the provider is back.
    monkeypatch.undo()
    manual = client.post(f"/finance/loans/{loan.id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert manual.status_code == 200, manual.text


def test_manual_disbursement_fails_cleanly_when_gateway_refuses(client, engine, monkeypatch):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _approve(client, ctx)
    monkeypatch.setattr(disbursement, "get_gateway", lambda: FailingGateway())
    resp = client.post(f"/finance/loans/{_loan(engine, ctx).id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert resp.status_code == 502
    assert _loan(engine, ctx).status == LoanStatus.approved


def test_suspended_company_is_not_auto_disbursed(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _settings(client, ctx, auto_disburse_enabled=True, auto_disburse_max_amount="10000.00")
    _approve(client, ctx)  # disbursed on approval; set up a second loan state instead:
    with Session(engine) as session, tenant_context(ctx["company"]["id"]):
        loan = session.exec(select(Loan)).first()
        loan.status = LoanStatus.approved
        loan.disbursed_at = None
        session.add(loan)
        company = session.get(Company, ctx["company"]["id"])
        company.status = CompanyStatus.suspended
        session.add(company)
        session.commit()
        assert disbursement.maybe_auto_disburse(session, loan.id) is False
        assert session.get(Loan, loan.id).status == LoanStatus.approved


# --- STK push reminders --------------------------------------------------------


def _active_loan_with_instalment_due(client, engine, ctx, *, days_ago=0):
    _approve(client, ctx)
    loan = _loan(engine, ctx)
    manual = client.post(f"/finance/loans/{loan.id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert manual.status_code == 200, manual.text
    with Session(engine) as session, tenant_context(ctx["company"]["id"]):
        schedule = session.exec(select(RepaymentSchedule)).first()
        schedule.due_date = business_today() - timedelta(days=days_ago)
        session.add(schedule)
        session.commit()


def _at(hour, day_offset=0) -> datetime:
    return datetime.combine(business_today() + timedelta(days=day_offset), datetime.min.time(), NAIROBI).replace(hour=hour)


def _run(engine, when):
    with Session(engine) as session:
        return run_stk_reminders(session, now=when)


def _prompts(engine, ctx) -> int:
    return _audit_actions(engine, ctx).count(AuditAction.STK_PUSH_REQUESTED.value)


def test_stk_reminders_do_nothing_unless_enabled(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _active_loan_with_instalment_due(client, engine, ctx)
    assert _run(engine, _at(10)).sent == 0
    assert _prompts(engine, ctx) == 0


def test_stk_prompts_due_instalment_once_a_day_with_limits(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _active_loan_with_instalment_due(client, engine, ctx)
    assert _settings(client, ctx, stk_push_enabled=True).status_code == 200

    assert _run(engine, _at(10)).sent == 1  # due today
    assert _run(engine, _at(11)).sent == 0  # same day: never twice
    assert _run(engine, _at(10, 1)).sent == 0  # 1 day later: too soon
    assert _run(engine, _at(10, 3)).sent == 1  # 3 days later: second prompt
    assert _run(engine, _at(10, 6)).sent == 1  # third prompt
    assert _run(engine, _at(10, 9)).sent == 0  # capped at three
    assert _prompts(engine, ctx) == 3


def test_stk_only_inside_business_hours(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _active_loan_with_instalment_due(client, engine, ctx)
    _settings(client, ctx, stk_push_enabled=True)
    for hour in (3, 7, 19, 23):
        result = _run(engine, _at(hour))
        assert result.skipped_outside_hours and result.sent == 0
    assert _prompts(engine, ctx) == 0
    assert _run(engine, _at(8)).sent == 1


def test_stk_skips_future_paid_and_suspended(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _active_loan_with_instalment_due(client, engine, ctx, days_ago=-5)  # not due yet
    _settings(client, ctx, stk_push_enabled=True)
    assert _run(engine, _at(10)).sent == 0

    with Session(engine) as session, tenant_context(ctx["company"]["id"]):
        schedule = session.exec(select(RepaymentSchedule)).first()
        schedule.due_date = business_today()
        session.add(schedule)
        company = session.get(Company, ctx["company"]["id"])
        company.status = CompanyStatus.suspended
        session.add(company)
        session.commit()
    assert _run(engine, _at(10)).sent == 0  # suspended company: no prompts

    with Session(engine) as session, tenant_context(ctx["company"]["id"]):
        company = session.get(Company, ctx["company"]["id"])
        company.status = CompanyStatus.active
        session.add(company)
        schedule = session.exec(select(RepaymentSchedule)).first()
        schedule.is_paid = True
        session.add(schedule)
        session.commit()
    assert _run(engine, _at(10)).sent == 0  # paid: nothing to ask for


def test_stk_failure_is_audited_and_counts_as_an_attempt(client, engine, monkeypatch):
    from app import stk_reminders

    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    _active_loan_with_instalment_due(client, engine, ctx)
    _settings(client, ctx, stk_push_enabled=True)
    monkeypatch.setattr(stk_reminders, "get_gateway", lambda: FailingGateway())

    result = _run(engine, _at(10))
    assert (result.sent, result.failed) == (0, 1)
    assert _prompts(engine, ctx) == 1  # recorded, so it is not retried the same day
    assert _run(engine, _at(11)).failed == 0
