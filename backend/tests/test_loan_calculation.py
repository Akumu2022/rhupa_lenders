"""CLAUDE.md §23: "the money-critical module... heavily unit-tested — first
module to get real tests; each interest model tested separately." These tests
exercise app/loan_calculation.py directly, with no HTTP/DB involved, so every
interest model and the penalty/cap engine can be pinned down independently of
what any single seeded product currently configures.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from app.loan_calculation import (
    _penalty_cap,
    apply_daily_penalties,
    generate_schedule,
    round_money,
)
from app.models import InterestModel, Loan, LoanProduct, PenaltyType, RepaymentSchedule, Transaction
from app.tenancy import tenant_context


@pytest.fixture()
def session(engine):
    """A DB session pre-scoped to a single company — app/loan_calculation.py
    queries tenant-owned models (RepaymentSchedule), which requires an active
    tenant_context (CLAUDE.md §5)."""
    with tenant_context(1):
        with Session(engine) as db_session:
            yield db_session


def test_round_money_half_up_to_the_cent():
    assert round_money(Decimal("10.005")) == Decimal("10.01")
    assert round_money(Decimal("10.004")) == Decimal("10.00")
    assert round_money(Decimal("10.015")) == Decimal("10.02")


# ---------------------------------------------------------------------------
# flat
# ---------------------------------------------------------------------------


def test_flat_single_installment_matches_principal_times_rate():
    schedule = generate_schedule(
        principal=Decimal("5000.00"),
        rate_percent=Decimal("5.00"),
        interest_model=InterestModel.flat,
        term_days=30,
        installment_count=1,
        start_date=date(2026, 1, 1),
    )
    assert len(schedule.installments) == 1
    installment = schedule.installments[0]
    assert installment.principal_component == Decimal("5000.00")
    assert installment.interest_component == Decimal("250.00")  # 5% of 5000
    assert installment.amount_due == Decimal("5250.00")
    assert installment.due_date == date(2026, 1, 31)
    assert schedule.total_repayable == Decimal("5250.00")


def test_flat_interest_is_independent_of_term_length():
    """"principal x rate, fixed" — a longer term does not change the interest."""
    short = generate_schedule(
        principal=Decimal("5000.00"), rate_percent=Decimal("5.00"), interest_model=InterestModel.flat,
        term_days=7, installment_count=1, start_date=date(2026, 1, 1),
    )
    long = generate_schedule(
        principal=Decimal("5000.00"), rate_percent=Decimal("5.00"), interest_model=InterestModel.flat,
        term_days=90, installment_count=1, start_date=date(2026, 1, 1),
    )
    assert short.total_interest == long.total_interest == Decimal("250.00")


def test_flat_multi_installment_splits_evenly_and_sums_exactly():
    schedule = generate_schedule(
        principal=Decimal("1000.00"), rate_percent=Decimal("10.00"), interest_model=InterestModel.flat,
        term_days=90, installment_count=3, start_date=date(2026, 1, 1),
    )
    assert len(schedule.installments) == 3
    # 1000 / 3 doesn't divide evenly — the remainder lands on the last installment.
    assert [i.principal_component for i in schedule.installments] == [
        Decimal("333.33"), Decimal("333.33"), Decimal("333.34"),
    ]
    assert schedule.total_principal == Decimal("1000.00")
    assert schedule.total_interest == Decimal("100.00")  # 10% of 1000, flat
    assert sum((i.amount_due for i in schedule.installments), Decimal("0.00")) == schedule.total_repayable
    assert [i.due_date for i in schedule.installments] == [date(2026, 1, 31), date(2026, 3, 2), date(2026, 4, 1)]


# ---------------------------------------------------------------------------
# reducing_balance
# ---------------------------------------------------------------------------


def test_reducing_balance_single_installment_matches_flat():
    """With only one installment there's no balance left to "reduce" yet —
    genuinely identical to flat until installment_count > 1."""
    schedule = generate_schedule(
        principal=Decimal("5000.00"), rate_percent=Decimal("5.00"), interest_model=InterestModel.reducing_balance,
        term_days=30, installment_count=1, start_date=date(2026, 1, 1),
    )
    assert schedule.total_interest == Decimal("250.00")


def test_reducing_balance_interest_shrinks_each_installment():
    schedule = generate_schedule(
        principal=Decimal("3000.00"), rate_percent=Decimal("10.00"), interest_model=InterestModel.reducing_balance,
        term_days=90, installment_count=3, start_date=date(2026, 1, 1),
    )
    # Equal principal shares (1000 each); interest computed on the balance
    # OUTSTANDING BEFORE each installment: 3000, then 2000, then 1000.
    interests = [i.interest_component for i in schedule.installments]
    assert interests == [Decimal("300.00"), Decimal("200.00"), Decimal("100.00")]
    assert interests[0] > interests[1] > interests[2]
    assert schedule.total_principal == Decimal("3000.00")


def test_reducing_balance_total_interest_is_less_than_charging_the_full_rate_every_period():
    """CLAUDE.md §23: reducing_balance's rate is per-installment-period,
    applied to whatever balance remains — the shrinking balance must produce
    LESS total interest than if the full rate were (wrongly) charged against
    the full original principal every single period."""
    schedule = generate_schedule(
        principal=Decimal("3000.00"), rate_percent=Decimal("10.00"), interest_model=InterestModel.reducing_balance,
        term_days=90, installment_count=3, start_date=date(2026, 1, 1),
    )
    naive_full_principal_every_period = Decimal("3000.00") * Decimal("10.00") / Decimal("100") * 3
    assert schedule.total_interest < naive_full_principal_every_period


# ---------------------------------------------------------------------------
# daily_accrual
# ---------------------------------------------------------------------------


def test_daily_accrual_single_installment_scales_with_term_days():
    """Unlike flat, daily_accrual genuinely differs even with one installment:
    interest = principal * daily_rate * number_of_days."""
    schedule = generate_schedule(
        principal=Decimal("5000.00"), rate_percent=Decimal("0.50"), interest_model=InterestModel.daily_accrual,
        term_days=14, installment_count=1, start_date=date(2026, 1, 1),
    )
    # 5000 * 0.5% * 14 days = 350.00
    assert schedule.total_interest == Decimal("350.00")

    longer = generate_schedule(
        principal=Decimal("5000.00"), rate_percent=Decimal("0.50"), interest_model=InterestModel.daily_accrual,
        term_days=28, installment_count=1, start_date=date(2026, 1, 1),
    )
    assert longer.total_interest == Decimal("700.00")


def test_daily_accrual_multi_installment_uses_remaining_balance_and_period_length():
    schedule = generate_schedule(
        principal=Decimal("3000.00"), rate_percent=Decimal("1.00"), interest_model=InterestModel.daily_accrual,
        term_days=30, installment_count=3, start_date=date(2026, 1, 1),
    )
    # Each period is 10 days; principal shares are 1000 each; balance before
    # each period is 3000, then 2000, then 1000.
    interests = [i.interest_component for i in schedule.installments]
    assert interests == [Decimal("300.00"), Decimal("200.00"), Decimal("100.00")]


# ---------------------------------------------------------------------------
# penalties + cap
# ---------------------------------------------------------------------------


def _product(**overrides) -> LoanProduct:
    defaults = dict(
        company_id=1, name="Test Product", min_amount=Decimal("100.00"), max_amount=Decimal("100000.00"),
        interest_rate=Decimal("5.00"), repayment_period_days=30, penalty_type=PenaltyType.percentage_per_day,
        penalty_rate=Decimal("1.00"), grace_period_days=3, penalty_cap_ratio=Decimal("1.00"),
    )
    defaults.update(overrides)
    return LoanProduct(**defaults)


def _loan(**overrides) -> Loan:
    defaults = dict(
        application_id=1, customer_id=1, loan_product_id=1, company_id=1,
        principal=Decimal("5000.00"), interest_rate=Decimal("5.00"),
        total_repayable=Decimal("5250.00"), outstanding_balance=Decimal("5250.00"),
    )
    defaults.update(overrides)
    return Loan(**defaults)


def test_no_penalty_within_grace_period(session):
    product = _product()
    loan = _loan()
    session.add(product)
    session.add(loan)
    session.flush()
    session.add(
        RepaymentSchedule(
            loan_id=loan.id, company_id=1, installment_number=1,
            due_date=date(2026, 1, 1), amount_due=Decimal("5250.00"),
            principal_component=Decimal("5000.00"), interest_component=Decimal("250.00"),
        )
    )
    session.flush()

    # 2 days overdue, grace is 3 — still within grace, no penalty yet.
    apply_daily_penalties(session, loan, product, today=date(2026, 1, 3))
    session.commit()
    session.refresh(loan)
    assert loan.penalties_accrued == Decimal("0.00")
    assert loan.outstanding_balance == Decimal("5250.00")


def test_penalty_applied_per_day_past_grace_and_compounds(session):
    product = _product()
    loan = _loan()
    session.add(product)
    session.add(loan)
    session.flush()
    session.add(
        RepaymentSchedule(
            loan_id=loan.id, company_id=1, installment_number=1,
            due_date=date(2026, 1, 1), amount_due=Decimal("5250.00"),
            principal_component=Decimal("5000.00"), interest_component=Decimal("250.00"),
        )
    )
    session.flush()

    # due_date + grace(3) = Jan 4 is the first penalty date. 5 days overdue
    # (today = Jan 6) means penalty days are Jan 4, 5, 6 — three days.
    apply_daily_penalties(session, loan, product, today=date(2026, 1, 6))
    session.commit()
    session.refresh(loan)

    # Day 1: 5250.00 * 1% = 52.50 -> 5302.50
    # Day 2: 5302.50 * 1% = 53.025 -> round half up -> 53.03 -> 5355.53
    # Day 3: 5355.53 * 1% = 53.5553 -> 53.56 -> 5409.09
    assert loan.penalties_accrued == Decimal("159.09")
    assert loan.outstanding_balance == Decimal("5409.09")

    penalty_transactions = session.exec(
        select(Transaction).where(Transaction.type == "penalty")
    ).all()
    assert len(penalty_transactions) == 3
    assert sum((t.amount for t in penalty_transactions), Decimal("0.00")) == Decimal("159.09")


def test_penalty_application_is_idempotent_for_the_same_day(session):
    product = _product()
    loan = _loan()
    session.add(product)
    session.add(loan)
    session.flush()
    session.add(
        RepaymentSchedule(
            loan_id=loan.id, company_id=1, installment_number=1,
            due_date=date(2026, 1, 1), amount_due=Decimal("5250.00"),
            principal_component=Decimal("5000.00"), interest_component=Decimal("250.00"),
        )
    )
    session.flush()

    apply_daily_penalties(session, loan, product, today=date(2026, 1, 6))
    session.commit()
    session.refresh(loan)
    first_balance = loan.outstanding_balance

    # Calling again for the SAME day must not double-apply.
    apply_daily_penalties(session, loan, product, today=date(2026, 1, 6))
    session.commit()
    session.refresh(loan)
    assert loan.outstanding_balance == first_balance


def test_penalty_capped_at_penalty_cap_ratio_of_principal(session):
    # Cap set tight so it's reachable in a small number of days for the test.
    product = _product(penalty_cap_ratio=Decimal("0.06"))  # 6% of principal, on top of the 5% base interest
    loan = _loan()
    session.add(product)
    session.add(loan)
    session.flush()
    session.add(
        RepaymentSchedule(
            loan_id=loan.id, company_id=1, installment_number=1,
            due_date=date(2026, 1, 1), amount_due=Decimal("5250.00"),
            principal_component=Decimal("5000.00"), interest_component=Decimal("250.00"),
        )
    )
    session.flush()

    # cap = 5000 * 0.06 = 300.00; base_interest already uses 250.00 of that,
    # leaving only 50.00 of headroom for penalties before accrual must stop.
    apply_daily_penalties(session, loan, product, today=date(2026, 1, 20))
    session.commit()
    session.refresh(loan)

    assert loan.penalties_accrued == Decimal("50.00")
    assert loan.outstanding_balance == Decimal("5300.00")

    penalty_transactions = session.exec(
        select(Transaction).where(Transaction.type == "penalty")
    ).all()
    assert sum((t.amount for t in penalty_transactions), Decimal("0.00")) == Decimal("50.00")

    # A later call finds no headroom left and applies nothing further.
    apply_daily_penalties(session, loan, product, today=date(2026, 1, 25))
    session.commit()
    session.refresh(loan)
    assert loan.penalties_accrued == Decimal("50.00")


def test_penalty_cap_helper():
    product = _product(penalty_cap_ratio=Decimal("1.00"))
    loan = _loan(principal=Decimal("5000.00"))
    assert _penalty_cap(loan, product) == Decimal("5000.00")
