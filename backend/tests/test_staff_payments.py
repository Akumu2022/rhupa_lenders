"""Staff-recorded repayments (POST /loans/{id}/payments): cashier and credit
officer record money the borrower paid them; same balance/schedule/ledger
path as self-service, with a receipt number and a once-only reference."""

from sqlmodel import Session, select

from app.models import AuditLog, Loan, Transaction, TransactionType, User
from app.tenancy import tenant_context
from tests.test_credit import _auth_headers, _setup_company_with_branch_review_application
from tests.test_finance import _approve_and_disburse


def _pay(client, token, loan_id, **body):
    return client.post(f"/loans/{loan_id}/payments", json=body, headers=_auth_headers(token))


def test_cashier_records_mpesa_payment_with_receipt_and_audit(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)

    resp = _pay(client, ctx["finance_token"], loan_id, amount="1500.00", method="mpesa", reference="qab12 cd")
    assert resp.status_code == 201, resp.text
    receipt = resp.json()
    assert receipt["receipt_number"].startswith("RCT-")
    assert receipt["reference"] == "QAB12CD"  # normalized
    assert receipt["received_by_name"] == "Finance One"
    assert receipt["customer_full_name"] == "Customer One"

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loan = session.get(Loan, loan_id)
            assert receipt["outstanding_balance_after"] == str(loan.outstanding_balance)
            txn = session.exec(select(Transaction).where(Transaction.type == TransactionType.repayment)).one()
            assert txn.method.value == "mpesa"
            assert txn.recorded_by is not None
            audit = session.exec(select(AuditLog).where(AuditLog.action == "loan.payment_recorded")).one()
            assert "QAB12CD" in audit.reason


def test_same_reference_cannot_be_recorded_twice(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)

    assert _pay(client, ctx["finance_token"], loan_id, amount="500.00", method="mpesa", reference="QAB12CD").status_code == 201
    dup = _pay(client, ctx["credit_token"], loan_id, amount="500.00", method="mpesa", reference="qab12cd")
    assert dup.status_code == 409
    assert "already recorded" in dup.json()["detail"]


def test_mpesa_and_bank_require_reference_cash_does_not(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)

    assert _pay(client, ctx["finance_token"], loan_id, amount="100.00", method="mpesa").status_code == 422
    assert _pay(client, ctx["finance_token"], loan_id, amount="100.00", method="bank", reference="  ").status_code == 422
    first = _pay(client, ctx["finance_token"], loan_id, amount="100.00", method="cash")
    second = _pay(client, ctx["finance_token"], loan_id, amount="100.00", method="cash")
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["receipt_number"] != second.json()["receipt_number"]


def test_credit_officer_can_record_for_own_branch_only(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)
    assert _pay(client, ctx["credit_token"], loan_id, amount="200.00", method="cash").status_code == 201

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            officer = session.exec(select(User).where(User.email == "credit@companya.example.com")).one()
            other = create_other_branch(client, ctx)
            officer.branch_id = other
            session.add(officer)
            session.commit()
    assert _pay(client, ctx["credit_token"], loan_id, amount="200.00", method="cash").status_code == 404


def create_other_branch(client, ctx) -> int:
    from tests.conftest import create_branch

    return create_branch(client, ctx["admin_token"], name="Second", code="SECOND")["id"]


def test_full_payment_closes_loan_and_overpayment_rejected(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            owed = session.get(Loan, loan_id).outstanding_balance

    too_much = _pay(client, ctx["finance_token"], loan_id, amount=str(owed + 1), method="cash")
    assert too_much.status_code == 400
    full = _pay(client, ctx["finance_token"], loan_id, amount=str(owed), method="cash")
    assert full.status_code == 201
    assert full.json()["loan_status"] == "repaid"
    assert _pay(client, ctx["finance_token"], loan_id, amount="1.00", method="cash").status_code == 400


def test_other_roles_cannot_record_payments(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)
    for token in (ctx["manager_token"], ctx["customer_token"], ctx["admin_token"]):
        assert _pay(client, token, loan_id, amount="100.00", method="cash").status_code == 403


def test_cannot_record_payment_on_another_companys_loan(client, engine):
    a = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    b = _setup_company_with_branch_review_application(
        client, engine, company_name="Company B", platform_token=a["platform_token"], include_finance=True
    )
    b_loan = _approve_and_disburse(client, engine, b)
    assert _pay(client, a["finance_token"], b_loan, amount="100.00", method="cash").status_code == 404


def test_timeline_shows_payment_method_reference_and_receipt(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)
    receipt = _pay(client, ctx["finance_token"], loan_id, amount="700.00", method="mpesa", reference="QXY99").json()

    timeline = client.get(
        f"/analytics/applications/{ctx['application']['id']}/timeline", headers=_auth_headers(ctx["credit_token"])
    ).json()
    payment = next(e for e in timeline["events"] if e["kind"] == "repayment")
    assert payment["actor_name"] == "Finance One"
    assert "M-Pesa" in payment["detail"] and "QXY99" in payment["detail"] and receipt["receipt_number"] in payment["detail"]


def test_customer_self_service_repayment_still_works_and_gets_receipt(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)
    resp = client.post(f"/loans/{loan_id}/repay", json={"amount": "300.00"}, headers=_auth_headers(ctx["customer_token"]))
    assert resp.status_code == 200, resp.text
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            txn = session.exec(select(Transaction).where(Transaction.type == TransactionType.repayment)).one()
            assert txn.method.value == "customer_portal"
            assert txn.recorded_by is None
            assert txn.receipt_number is not None
