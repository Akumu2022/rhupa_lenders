"""Postgres row-level security: the database-level backstop to the tenant
scoping in app/tenancy.py (CLAUDE.md §5, "RLS is the only backstop that
catches a bug in the central mechanism itself").

Two halves:

1. Policies. Every tenant-owned table gets one policy: a row is visible or
   writable only when its company_id matches the connection's
   `app.company_id` setting, or when `app.bypass` is 'on' (the explicit
   platform scope, tenant_context(None)). Unset means nothing matches, so a
   query with no scope sees nothing: fail closed, like the ORM filter.
   Policies are ENABLED by migration; they bind the app's own role only once
   FORCE ROW LEVEL SECURITY is switched on (the app's role owns the tables,
   and Postgres exempts owners unless forced).

2. Per-connection scope. Before each statement on a Postgres connection, the
   current tenant scope (tenancy.current_scope) is written to those two
   settings, only when it differs from what the connection already holds.
   The cached value is dropped on every pool checkout and on rollback
   (a rolled-back set_config reverts), so a stale scope can never leak into
   the next request.

SQLite (dev/tests) has no RLS; everything here is a no-op there.
"""

from sqlalchemy import DDL, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import Pool
from sqlmodel import SQLModel

from . import models  # noqa: F401 — registers every table on SQLModel.metadata
from .tenancy import _UNSET, current_scope

# Every table carrying company_id. tests/test_rls_config.py fails if a new
# tenant-owned model is added without being listed here (rule #12 spirit).
TENANT_TABLES = (
    "applicationreviewstage",
    "auditlog",
    "branch",
    "businessassessment",
    "expenseentry",
    "guarantor",
    "loan",
    "loanapplication",
    "loanproduct",
    "mfarecoverycode",
    "profile",
    "referee",
    "repaymentschedule",
    "security",
    "transaction",
    "user",
)

POLICY_PREDICATE = (
    "current_setting('app.bypass', true) = 'on' "
    "OR company_id::text = current_setting('app.company_id', true)"
)


def policy_statements(table: str) -> list[str]:
    """Idempotent DDL enabling (not forcing) RLS with the tenant policy."""
    return [
        f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY',
        f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"',
        f'CREATE POLICY tenant_isolation ON "{table}" USING ({POLICY_PREDICATE}) WITH CHECK ({POLICY_PREDICATE})',
    ]


def force_statements(table: str) -> list[str]:
    return [f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY']


# Fresh databases (tests on Postgres, a brand-new deploy) get the policies
# from create_all; existing ones get them from migration d5a7c9e1f3b6.
for _table_name in TENANT_TABLES:
    _table = SQLModel.metadata.tables[_table_name]
    for _statement in policy_statements(_table_name):
        event.listen(_table, "after_create", DDL(_statement).execute_if(dialect="postgresql"))


_STATE_KEY = "rls_scope"


def _desired_settings() -> tuple[str, str]:
    scope = current_scope()
    if scope is None:
        return ("on", "")  # explicit platform bypass
    if scope is _UNSET:
        return ("off", "")  # no scope: policies match nothing
    return ("off", str(scope))


@event.listens_for(Engine, "before_cursor_execute")
def _apply_scope(conn, cursor, statement, parameters, context, executemany):
    if conn.dialect.name != "postgresql":
        return
    desired = _desired_settings()
    if conn.info.get(_STATE_KEY) == desired:
        return
    # A separate raw DB-API cursor: no SQLAlchemy events fire for it, so no
    # recursion, and the main statement's cursor is left untouched.
    raw = cursor.connection.cursor()
    try:
        raw.execute(
            "SELECT set_config('app.bypass', %s, false), set_config('app.company_id', %s, false)",
            desired,
        )
    finally:
        raw.close()
    conn.info[_STATE_KEY] = desired


@event.listens_for(Engine, "rollback")
def _forget_on_rollback(conn):
    conn.info.pop(_STATE_KEY, None)


@event.listens_for(Engine, "rollback_savepoint")
def _forget_on_savepoint_rollback(conn, name, context):
    conn.info.pop(_STATE_KEY, None)


@event.listens_for(Pool, "checkout")
def _forget_on_checkout(dbapi_connection, connection_record, connection_proxy):
    connection_record.info.pop(_STATE_KEY, None)
