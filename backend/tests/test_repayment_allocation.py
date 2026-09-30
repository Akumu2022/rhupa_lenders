"""Repayment allocation order: penalties -> interest -> principal (the
standard for Kenyan lenders, confirmed by Finance)."""

from datetime import date, timedelta
from decimal import Decimal

from sqlmodel import Session, select

from app.loan_analytics import balance_split
from app.models import Loan, RepaymentSchedule, Transaction, TransactionType
from app.repayments import allocate_payment
from app.tenancy import tenant_context
from app.time_utils import business_today
from tests.test_credit import _auth_headers, _setup_company_with_branch_review_application
from tests.test_finance import _approve_and_disburse

D = Decimal


def _loan(principal="1000.00", total="1200.00", penalties="0.00", penalties_repaid="0.00"):
    return Loan(
        application_id=1, customer_id=1, loan_product_id=1, company_id=1,
        principal=D(principal), interest_rate=D("20.00"), total_repayable=D(total),
        outstanding_balance=D(total) + D(penalties) - D(penalties_repaid),
        penalties_accrued=D(penalties), penalties_repaid=D(penalties_repaid),
    )


def _inst(n, due, interest, paid="0.00"):
    due, interest = D(due), D(interest)
    return RepaymentSchedule(
        loan_id=1, company_id=1, installment_number=n, due_date=date(2026, 1, n),
        amount_due=due, amount_paid=D(paid), principal_component=due - interest, interest_component=interest,
    )


def test_penalties_are_cleared_before_interest_and_principal():
    split = allocate_payment(_loan(penalties="50.00"), D("80.00"), [_inst(1, "1200.00", "200.00")])
    assert (split.penalty, split.interest, split.principal) == (D("50.00"), D("30.00"), D("0.00"))
    assert split.installments[0][1] == D("30.00")  # penalties never touch the schedule


def test_interest_before_principal_within_an_instalment():
    split = allocate_payment(_loan(), D("250.00"), [_inst(1, "1200.00", "200.00")])
    assert (split.penalty, split.interest, split.principal) == (D("0.00"), D("200.00"), D("50.00"))


def test_oldest_instalment_is_settled_first():
    schedule = [_inst(1, "600.00", "100.00"), _inst(2, "600.00", "100.00")]
    split = allocate_payment(_loan(), D("700.00"), schedule)
    # Instalment 1 fully (100 interest + 500 principal), then instalment 2's interest.
    assert (split.interest, split.principal) == (D("200.00"), D("500.00"))
    assert [a for _, a in split.installments] == [D("600.00"), D("100.00")]


def test_partly_paid_instalment_resumes_where_it_left_off():
    # 150 already paid on this instalment = 150 of its 200 interest.
    split = allocate_payment(_loan(), D("100.00"), [_inst(1, "1200.00", "200.00", paid="150.00")])
    assert (split.interest, split.principal) == (D("50.00"), D("50.00"))


def test_already_repaid_penalties_are_not_charged_again():
    split = allocate_payment(_loan(penalties="50.00", penalties_repaid="50.00"), D("10.00"), [_inst(1, "1200.00", "200.00")])
    assert (split.penalty, split.interest) == (D("0.00"), D("10.00"))


def test_overdue_loan_payment_goes_to_penalties_first_end_to_end(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            inst = session.exec(select(RepaymentSchedule).where(RepaymentSchedule.loan_id == loan_id)).first()
            inst.due_date = business_today() - timedelta(days=6)  # past the 3-day grace -> penalties accrue
            session.add(inst)
            session.commit()

    # Any read path runs the delinquency sync, which applies penalties.
    client.get("/analytics/dashboard", headers=_auth_headers(ctx["finance_token"]))
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loan = session.get(Loan, loan_id)
            penalties = loan.penalties_accrued
            interest = loan.total_repayable - loan.principal
    assert penalties > 0

    pay = penalties + interest + D("100.00")
    resp = client.post(
        f"/loans/{loan_id}/payments", json={"amount": str(pay), "method": "cash"}, headers=_auth_headers(ctx["finance_token"])
    )
    assert resp.status_code == 201, resp.text
    receipt = resp.json()
    assert D(receipt["penalty_portion"]) == penalties
    assert D(receipt["interest_portion"]) == interest
    assert D(receipt["principal_portion"]) == D("100.00")

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loan = session.get(Loan, loan_id)
            assert loan.penalties_repaid == penalties
            assert loan.interest_repaid == interest
            assert loan.principal_repaid == D("100.00")
            split = balance_split(loan)
            # The stored totals always reconcile with the outstanding balance.
            assert split.principal + split.interest + split.penalties == loan.outstanding_balance
            assert split.principal == loan.principal - D("100.00")
            txn = session.exec(select(Transaction).where(Transaction.type == TransactionType.repayment)).one()
            assert txn.penalty_portion == penalties


def test_full_repayment_zeroes_every_component(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    loan_id = _approve_and_disburse(client, engine, ctx)
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            owed = session.get(Loan, loan_id).outstanding_balance
    client.post(f"/loans/{loan_id}/repay", json={"amount": str(owed)}, headers=_auth_headers(ctx["customer_token"]))
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loan = session.get(Loan, loan_id)
            split = balance_split(loan)
            assert (split.principal, split.interest, split.penalties) == (D("0.00"), D("0.00"), D("0.00"))
            assert loan.principal_repaid == loan.principal
            assert loan.status.value == "repaid"


def test_legacy_instalment_without_interest_split_never_overpays_principal():
    # Created before instalments carried a split: interest_component = 0.
    loan = _loan(principal="1000.00", total="1200.00")
    loan.principal_repaid = D("900.00")
    loan.outstanding_balance = D("300.00")
    split = allocate_payment(loan, D("300.00"), [_inst(1, "1200.00", "0.00", paid="900.00")])
    assert (split.principal, split.interest) == (D("100.00"), D("200.00"))
