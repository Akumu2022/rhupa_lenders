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


def _platform_token(client, engine):
    from tests.conftest import seed_super_admin
    from tests.test_credit import _login

    seed_super_admin(engine, email="platform@rupha.example.com", password="platform-pass-1")
    return _login(client, "platform@rupha.example.com", "platform-pass-1")


def test_security_status_is_super_admin_only(client, engine):
    token = _platform_token(client, engine)
    resp = client.get("/platform/security", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    if TEST_DATABASE_URL:
        # CI's Postgres: ordinary role, policies forced on every table.
        assert body["role_bypasses_rls"] is False
        assert body["enforced"] is True
        assert {t["table"] for t in body["tables"]} == set(TENANT_TABLES)
    else:
        assert body == {"database": "sqlite", "role": None, "role_bypasses_rls": None, "enforced": False, "tables": []}


def test_app_db_role_must_be_a_plain_role_name(monkeypatch):
    from app import rls
    from app.config import settings

    monkeypatch.setattr(settings, "app_db_role", "x; DROP TABLE loan")
    with pytest.raises(RuntimeError):
        rls._app_role()


@postgres_only
def test_app_switches_to_app_db_role_each_transaction(engine, monkeypatch):
    """APP_DB_ROLE: the app connects as one role and drops to the restricted
    one with SET LOCAL ROLE, re-applied in every transaction."""
    from sqlalchemy import create_engine

    from app.config import settings

    with engine.connect() as conn:
        me = conn.execute(text("SELECT current_user")).scalar()
    monkeypatch.setattr(settings, "app_db_role", me)  # a role can always SET ROLE to itself
    switching = create_engine(TEST_DATABASE_URL)
    try:
        with switching.connect() as conn:
            for _ in range(2):  # second time round: after a commit
                with tenant_context(7):
                    role, cid = conn.execute(
                        text("SELECT current_user, current_setting('app.company_id', true)")
                    ).one()
                assert (role, cid) == (me, "7")
                conn.commit()
            # Settings are transaction-local: nothing survives the commit on
            # the raw connection.
            raw = conn.connection.dbapi_connection.cursor()
            raw.execute("SELECT current_setting('app.company_id', true)")
            assert raw.fetchone()[0] in (None, "")
            raw.close()
    finally:
        switching.dispose()


@postgres_only
def test_unswitchable_app_db_role_falls_back_to_connecting_role(engine, monkeypatch):
    from sqlalchemy import create_engine

    from app.config import settings

    monkeypatch.setattr(settings, "app_db_role", "role_that_does_not_exist")
    switching = create_engine(TEST_DATABASE_URL)
    try:
        with tenant_context(None), switching.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1
    finally:
        switching.dispose()
