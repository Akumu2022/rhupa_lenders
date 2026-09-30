"""Row-level security (app/rls.py).

The configuration check runs everywhere. The enforcement tests run only
against Postgres (TEST_DATABASE_URL), where the conftest forces RLS on every
tenant table: they use raw SQL, bypassing the ORM tenant filter entirely,
to prove the database itself refuses to cross companies.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlmodel import Session, SQLModel

from app.models import Company, LoanProduct
from app.rls import TENANT_TABLES
from app.tenancy import tenant_context
from tests.conftest import TEST_DATABASE_URL

postgres_only = pytest.mark.skipif(not TEST_DATABASE_URL, reason="row-level security needs Postgres")


def test_every_tenant_table_is_protected():
    """A new model carrying company_id must be added to app/rls.py, or it
    silently gets no database-level protection."""
    with_company_id = {t.name for t in SQLModel.metadata.tables.values() if "company_id" in t.c}
    assert with_company_id == set(TENANT_TABLES)


def _two_companies_with_products(engine) -> tuple[int, int]:
    with Session(engine) as session:
        with tenant_context(None):
            a = Company(name="A", signup_code="rls-code-aaaaaaaa")
            b = Company(name="B", signup_code="rls-code-bbbbbbbb")
            session.add_all([a, b])
            session.commit()
            for company in (a, b):
                session.add(
                    LoanProduct(
                        company_id=company.id, name=f"P{company.id}", min_amount=Decimal("100"),
                        max_amount=Decimal("1000"), interest_rate=Decimal("5"), repayment_period_days=30,
                    )
                )
            session.commit()
            return a.id, b.id


@postgres_only
def test_tests_run_as_a_role_that_rls_applies_to(engine):
    """Superusers and BYPASSRLS roles skip row-level security, which would
    make every enforcement test here pass vacuously."""
    with engine.connect() as conn:
        exempt = conn.execute(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).scalar()
    assert exempt is False


@postgres_only
def test_raw_sql_sees_only_the_scoped_company(engine):
    a, b = _two_companies_with_products(engine)
    with tenant_context(a), engine.connect() as conn:
        rows = conn.execute(text("SELECT company_id FROM loanproduct")).scalars().all()
    assert rows == [a]


@postgres_only
def test_no_scope_sees_nothing(engine):
    _two_companies_with_products(engine)
    with engine.connect() as conn:  # no tenant_context at all
        assert conn.execute(text("SELECT count(*) FROM loanproduct")).scalar() == 0


@postgres_only
def test_platform_scope_sees_every_company(engine):
    _two_companies_with_products(engine)
    with tenant_context(None), engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM loanproduct")).scalar() == 2


@postgres_only
def test_cannot_write_a_row_into_another_company(engine):
    a, b = _two_companies_with_products(engine)
    columns = (
        "name, description, min_amount, max_amount, interest_rate, repayment_period_days, is_active, "
        "interest_model, installment_count, penalty_type, penalty_rate, grace_period_days, penalty_cap_ratio, "
        "branch_manager_delegated_limit, requires_guarantor"
    )
    with tenant_context(a), engine.connect() as conn:
        # Copy company A's own (visible) product, but stamp it with B's id.
        with pytest.raises(DatabaseError, match="row-level security"):
            conn.execute(
                text(f"INSERT INTO loanproduct (company_id, {columns}) SELECT :b, {columns} FROM loanproduct WHERE company_id = :a"),
                {"a": a, "b": b},
            )


@postgres_only
def test_update_cannot_reach_another_companys_row(engine):
    a, b = _two_companies_with_products(engine)
    with tenant_context(a), engine.begin() as conn:
        changed = conn.execute(text("UPDATE loanproduct SET name = 'hijacked' WHERE company_id = :b"), {"b": b}).rowcount
    assert changed == 0
