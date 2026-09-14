"""CLAUDE.md §5, rule #12: the tenant-scoping mechanism is proven by an automated
cross-company test suite that grows with every new tenant-owned model. This is a
merge gate, not a nice-to-have — a tenant-owned model added without an isolation
test for it is an incomplete change.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    Branch,
    BusinessAssessment,
    Company,
    Loan,
    LoanApplication,
    LoanProduct,
    Profile,
    Referee,
    RepaymentSchedule,
    Transaction,
    TransactionType,
    User,
    UserRole,
)
from app.tenancy import TenantScopeNotSetError, tenant_context


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture()
def seeded(engine):
    with Session(engine) as session:
        company_a = Company(name="Company A", signup_code="AAAAAAAAAA")
        company_b = Company(name="Company B", signup_code="BBBBBBBBBB")
        session.add(company_a)
        session.add(company_b)
        session.commit()
        session.refresh(company_a)
        session.refresh(company_b)
        company_a_id, company_b_id = company_a.id, company_b.id

        with tenant_context(None):  # platform bypass — seeding across tenants
            branch_a = Branch(company_id=company_a_id, name="A Main", code="A-MAIN")
            branch_b = Branch(company_id=company_b_id, name="B Main", code="B-MAIN")
            session.add(branch_a)
            session.add(branch_b)
            session.commit()

            user_a1 = User(
                email="a1@a.com",
                hashed_password="x",
                role=UserRole.customer,
                full_name="A One",
                company_id=company_a_id,
            )
            user_a2 = User(
                email="a2@a.com",
                hashed_password="x",
                role=UserRole.customer,
                full_name="A Two",
                company_id=company_a_id,
            )
            user_b1 = User(
                email="b1@b.com",
                hashed_password="x",
                role=UserRole.customer,
                full_name="B One",
                company_id=company_b_id,
            )
            session.add(user_a1)
            session.add(user_a2)
            session.add(user_b1)
            session.commit()
            session.refresh(user_a1)
            session.refresh(user_b1)

            profile_a1 = Profile(
                user_id=user_a1.id,
                company_id=company_a_id,
                date_of_birth=date(1990, 1, 1),
                national_id_number="A-NATID-1",
                phone_number="+254700000001",
                residential_address="A Address",
                employment_status="employed",
                monthly_income=Decimal("50000.00"),
                occupation="Teacher",
                id_document_path="1/1/fake.jpg",
            )
            profile_b1 = Profile(
                user_id=user_b1.id,
                company_id=company_b_id,
                date_of_birth=date(1992, 2, 2),
                national_id_number="B-NATID-1",
                phone_number="+254700000002",
                residential_address="B Address",
                employment_status="employed",
                monthly_income=Decimal("60000.00"),
                occupation="Nurse",
                id_document_path="2/1/fake.jpg",
            )
            session.add(profile_a1)
            session.add(profile_b1)
            session.commit()
            session.refresh(profile_a1)
            session.refresh(profile_b1)

            session.add(
                Referee(
                    company_id=company_a_id,
                    profile_id=profile_a1.id,
                    full_name="A Referee",
                    phone_number="+254700000011",
                )
            )
            session.add(
                Referee(
                    company_id=company_b_id,
                    profile_id=profile_b1.id,
                    full_name="B Referee",
                    phone_number="+254700000022",
                )
            )
            session.add(
                BusinessAssessment(
                    company_id=company_a_id,
                    profile_id=profile_a1.id,
                    business_name="A Kiosk",
                    business_type="Retail",
                    ownership="Sole proprietor",
                    physical_location="A Market",
                    years_in_operation=2,
                    sales_frequency="monthly",
                    total_income=Decimal("80000.00"),
                    total_expenses=Decimal("50000.00"),
                    existing_debt_obligations=Decimal("0.00"),
                    net_income=Decimal("30000.00"),
                    debt_service_capacity=Decimal("30000.00"),
                )
            )
            session.add(
                BusinessAssessment(
                    company_id=company_b_id,
                    profile_id=profile_b1.id,
                    business_name="B Kiosk",
                    business_type="Retail",
                    ownership="Sole proprietor",
                    physical_location="B Market",
                    years_in_operation=4,
                    sales_frequency="monthly",
                    total_income=Decimal("90000.00"),
                    total_expenses=Decimal("40000.00"),
                    existing_debt_obligations=Decimal("0.00"),
                    net_income=Decimal("50000.00"),
                    debt_service_capacity=Decimal("50000.00"),
                )
            )
            session.commit()

            product_a = LoanProduct(
                company_id=company_a_id,
                name="A Salary Advance",
                min_amount=Decimal("1000.00"),
                max_amount=Decimal("50000.00"),
                interest_rate=Decimal("5.00"),
                repayment_period_days=30,
            )
            product_b = LoanProduct(
                company_id=company_b_id,
                name="B Salary Advance",
                min_amount=Decimal("1000.00"),
                max_amount=Decimal("50000.00"),
                interest_rate=Decimal("5.00"),
                repayment_period_days=30,
            )
            session.add(product_a)
            session.add(product_b)
            session.commit()
            session.refresh(product_a)
            session.refresh(product_b)

            application_a = LoanApplication(
                company_id=company_a_id,
                customer_id=user_a1.id,
                loan_product_id=product_a.id,
                amount_requested=Decimal("10000.00"),
            )
            application_b = LoanApplication(
                company_id=company_b_id,
                customer_id=user_b1.id,
                loan_product_id=product_b.id,
                amount_requested=Decimal("20000.00"),
            )
            session.add(application_a)
            session.add(application_b)
            session.commit()
            session.refresh(application_a)
            session.refresh(application_b)

            loan_a = Loan(
                company_id=company_a_id,
                application_id=application_a.id,
                customer_id=user_a1.id,
                loan_product_id=product_a.id,
                principal=Decimal("10000.00"),
                interest_rate=Decimal("5.00"),
                total_repayable=Decimal("10500.00"),
                outstanding_balance=Decimal("10500.00"),
            )
            loan_b = Loan(
                company_id=company_b_id,
                application_id=application_b.id,
                customer_id=user_b1.id,
                loan_product_id=product_b.id,
                principal=Decimal("20000.00"),
                interest_rate=Decimal("5.00"),
                total_repayable=Decimal("21000.00"),
                outstanding_balance=Decimal("21000.00"),
            )
            session.add(loan_a)
            session.add(loan_b)
            session.commit()
            session.refresh(loan_a)
            session.refresh(loan_b)

            session.add(
                RepaymentSchedule(
                    company_id=company_a_id,
                    loan_id=loan_a.id,
                    installment_number=1,
                    due_date=date(2026, 1, 1),
                    amount_due=Decimal("10500.00"),
                )
            )
            session.add(
                RepaymentSchedule(
                    company_id=company_b_id,
                    loan_id=loan_b.id,
                    installment_number=1,
                    due_date=date(2026, 1, 1),
                    amount_due=Decimal("21000.00"),
                )
            )
            session.commit()

            session.add(
                Transaction(
                    company_id=company_a_id,
                    loan_id=loan_a.id,
                    customer_id=user_a1.id,
                    type=TransactionType.disbursement,
                    amount=Decimal("10000.00"),
                )
            )
            session.add(
                Transaction(
                    company_id=company_b_id,
                    loan_id=loan_b.id,
                    customer_id=user_b1.id,
                    type=TransactionType.disbursement,
                    amount=Decimal("20000.00"),
                )
            )
            session.commit()

    return {"engine": engine, "company_a_id": company_a_id, "company_b_id": company_b_id}


def test_scoped_query_returns_only_own_company_rows(seeded):
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            users = session.exec(select(User)).all()

    assert len(users) == 2
    assert all(u.company_id == seeded["company_a_id"] for u in users)


def test_scoped_query_cannot_reach_another_companys_row_by_direct_lookup(seeded):
    """The dangerous case: an attacker scoped to A tries to fetch a row that
    belongs to B by any predicate other than company_id. Must come back empty,
    not just filtered — a leak here is exactly the "one company sees another
    company's borrower" scenario CLAUDE.md §5 calls catastrophic."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            leaked = session.exec(select(User).where(User.email == "b1@b.com")).first()

    assert leaked is None


def test_unscoped_query_fails_closed(seeded):
    """No tenant_context() entered at all — e.g. a developer forgot to wire the
    auth dependency on some route. Must raise, never silently return all rows."""
    with Session(seeded["engine"]) as session:
        with pytest.raises(TenantScopeNotSetError):
            session.exec(select(User)).all()


def test_super_admin_platform_bypass_sees_all_companies(seeded):
    """The only sanctioned cross-company path: tenant_context(None), reserved for
    /platform/... routes gated on require_role("super_admin")."""
    with Session(seeded["engine"]) as session:
        with tenant_context(None):
            users = session.exec(select(User)).all()

    assert len(users) == 3
    assert {u.company_id for u in users} == {seeded["company_a_id"], seeded["company_b_id"]}


def test_branch_scoped_query_returns_only_own_company_rows(seeded):
    """CLAUDE.md §5/§25 rule #12: Branch was added in M10 — a company-scoped
    org unit, NOT a second tenant-isolation boundary, but it still inherits
    TenantMixin and so still gets the exact same merge-gate coverage as
    every other tenant-owned model."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            branches = session.exec(select(Branch)).all()

    assert len(branches) == 1
    assert branches[0].name == "A Main"
    assert branches[0].company_id == seeded["company_a_id"]


def test_branch_scoped_query_cannot_reach_another_companys_row_by_direct_lookup(seeded):
    """A leak here would expose another company's internal branch structure —
    the same catastrophic scenario CLAUDE.md §5 calls out by name."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            leaked = session.exec(select(Branch).where(Branch.code == "B-MAIN")).first()

    assert leaked is None


def test_branch_unscoped_query_fails_closed(seeded):
    with Session(seeded["engine"]) as session:
        with pytest.raises(TenantScopeNotSetError):
            session.exec(select(Branch)).all()


def test_profile_scoped_query_returns_only_own_company_rows(seeded):
    """CLAUDE.md §5 rule #12: Profile was added in M2 — this extends the
    merge-gate suite for it, same as every other tenant-owned model."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            profiles = session.exec(select(Profile)).all()

    assert len(profiles) == 1
    assert profiles[0].national_id_number == "A-NATID-1"
    assert profiles[0].company_id == seeded["company_a_id"]


def test_profile_scoped_query_cannot_reach_another_companys_row_by_direct_lookup(seeded):
    """A leak here would expose another company's borrower's national ID —
    exactly the catastrophic scenario CLAUDE.md §5 calls out by name."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            leaked = session.exec(
                select(Profile).where(Profile.national_id_number == "B-NATID-1")
            ).first()

    assert leaked is None


def test_loan_product_scoped_query_returns_only_own_company_rows(seeded):
    """CLAUDE.md §5 rule #12: LoanProduct/LoanApplication were added in M4."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            products = session.exec(select(LoanProduct)).all()

    assert len(products) == 1
    assert products[0].name == "A Salary Advance"


def test_loan_product_scoped_query_cannot_reach_another_companys_row(seeded):
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            leaked = session.exec(select(LoanProduct).where(LoanProduct.name == "B Salary Advance")).first()

    assert leaked is None


def test_loan_application_scoped_query_returns_only_own_company_rows(seeded):
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            applications = session.exec(select(LoanApplication)).all()

    assert len(applications) == 1
    assert applications[0].amount_requested == Decimal("10000.00")


def test_loan_application_scoped_query_cannot_reach_another_companys_row(seeded):
    """A leak here would expose another company's borrower's loan amount and
    application — exactly the cross-company data leak CLAUDE.md §5 forbids."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            leaked = session.exec(
                select(LoanApplication).where(LoanApplication.amount_requested == Decimal("20000.00"))
            ).first()

    assert leaked is None


def test_loan_scoped_query_returns_only_own_company_rows(seeded):
    """CLAUDE.md §5 rule #12: Loan and RepaymentSchedule were added in M5
    (credit-officer approval) — this extends the merge-gate suite for them."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            loans = session.exec(select(Loan)).all()

    assert len(loans) == 1
    assert loans[0].principal == Decimal("10000.00")
    assert loans[0].company_id == seeded["company_a_id"]


def test_loan_scoped_query_cannot_reach_another_companys_row(seeded):
    """A leak here would expose another company's borrower's loan balance —
    the same catastrophic scenario CLAUDE.md §5 calls out by name."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            leaked = session.exec(
                select(Loan).where(Loan.outstanding_balance == Decimal("21000.00"))
            ).first()

    assert leaked is None


def test_repayment_schedule_scoped_query_returns_only_own_company_rows(seeded):
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            schedules = session.exec(select(RepaymentSchedule)).all()

    assert len(schedules) == 1
    assert schedules[0].amount_due == Decimal("10500.00")
    assert schedules[0].company_id == seeded["company_a_id"]


def test_repayment_schedule_scoped_query_cannot_reach_another_companys_row(seeded):
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            leaked = session.exec(
                select(RepaymentSchedule).where(RepaymentSchedule.amount_due == Decimal("21000.00"))
            ).first()

    assert leaked is None


def test_transaction_scoped_query_returns_only_own_company_rows(seeded):
    """CLAUDE.md §5 rule #12: Transaction was added in M6 (its read side —
    the customer dashboard's transaction history; M7 is what writes to it)."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            transactions = session.exec(select(Transaction)).all()

    assert len(transactions) == 1
    assert transactions[0].amount == Decimal("10000.00")
    assert transactions[0].company_id == seeded["company_a_id"]


def test_transaction_scoped_query_cannot_reach_another_companys_row(seeded):
    """A leak here would expose another company's borrower's ledger entry —
    the same catastrophic scenario CLAUDE.md §5 calls out by name."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            leaked = session.exec(
                select(Transaction).where(Transaction.amount == Decimal("20000.00"))
            ).first()

    assert leaked is None


def test_referee_scoped_query_returns_only_own_company_rows(seeded):
    """CLAUDE.md §5/§27 rule #12: Referee was added in M11."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            referees = session.exec(select(Referee)).all()

    assert len(referees) == 1
    assert referees[0].full_name == "A Referee"
    assert referees[0].company_id == seeded["company_a_id"]


def test_referee_scoped_query_cannot_reach_another_companys_row(seeded):
    """A leak here would expose another company's borrower's referee contact
    details — the same catastrophic scenario CLAUDE.md §5 calls out by name."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            leaked = session.exec(select(Referee).where(Referee.full_name == "B Referee")).first()

    assert leaked is None


def test_referee_unscoped_query_fails_closed(seeded):
    with Session(seeded["engine"]) as session:
        with pytest.raises(TenantScopeNotSetError):
            session.exec(select(Referee)).all()


def test_business_assessment_scoped_query_returns_only_own_company_rows(seeded):
    """CLAUDE.md §5/§27 rule #12: BusinessAssessment was added in M11."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            assessments = session.exec(select(BusinessAssessment)).all()

    assert len(assessments) == 1
    assert assessments[0].business_name == "A Kiosk"
    assert assessments[0].company_id == seeded["company_a_id"]


def test_business_assessment_scoped_query_cannot_reach_another_companys_row(seeded):
    """A leak here would expose another company's borrower's business income
    and debt figures — the same catastrophic scenario CLAUDE.md §5 calls out
    by name."""
    with Session(seeded["engine"]) as session:
        with tenant_context(seeded["company_a_id"]):
            leaked = session.exec(
                select(BusinessAssessment).where(BusinessAssessment.business_name == "B Kiosk")
            ).first()

    assert leaked is None


def test_business_assessment_unscoped_query_fails_closed(seeded):
    with Session(seeded["engine"]) as session:
        with pytest.raises(TenantScopeNotSetError):
            session.exec(select(BusinessAssessment)).all()
