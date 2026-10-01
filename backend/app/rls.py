"""Postgres row-level security: the database-level backstop to the tenant
scoping in app/tenancy.py (CLAUDE.md §5, "RLS is the only backstop that
catches a bug in the central mechanism itself").

Three parts:

1. Policies. Every tenant-owned table gets one policy: a row is visible or
   writable only when its company_id matches the transaction's
   `app.company_id` setting, or when `app.bypass` is 'on' (the explicit
   platform scope, tenant_context(None)). Unset means nothing matches, so a
   query with no scope sees nothing: fail closed, like the ORM filter.
   Policies are ENABLED by migration, but the table owner (neondb_owner on
   Neon) is exempt from them.

2. Restricted role. The app connects with the owner's URL (one DATABASE_URL)
   and, when APP_DB_ROLE is set, switches to that restricted role with
   `SET LOCAL ROLE` at the start of every transaction. That role owns
   nothing and has no BYPASSRLS, so the policies bind it. Migrations never
   import this module, so they keep running as the owner. Whether the owner
   may switch to the role is probed once per physical connection; if it may
   not, the app logs an error and carries on as the owner (app-level
   isolation only) rather than failing every request.

3. Per-transaction scope. Before the first statement of each transaction on
   a Postgres connection, the role and the current tenant scope
   (tenancy.current_scope) are applied; within the transaction they are
   re-applied only when the scope changes. Everything is transaction-local
   (SET LOCAL / set_config(..., true)), because Neon's pooled endpoint is
   PgBouncer in transaction mode, where a session-level setting could
   outlive the request or reach another client. The cached value is dropped
   on commit, rollback and every pool checkout, so each transaction starts
   clean.

SQLite (dev/tests) has no RLS; everything here is a no-op there.
"""

import logging
import re

from sqlalchemy import DDL, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import Pool
from sqlmodel import SQLModel

from . import models  # noqa: F401 — registers every table on SQLModel.metadata
from .config import settings
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
# Per physical connection, kept across checkouts: may we SET ROLE to
# settings.app_db_role? Probed once, on connect.
_ROLE_OK_KEY = "rls_app_role_ok"

_ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")

logger = logging.getLogger(__name__)


def _app_role() -> str:
    role = settings.app_db_role.strip()
    if role and not _ROLE_NAME.match(role):
        raise RuntimeError(f"APP_DB_ROLE {role!r} is not a plain lowercase role name")
    return role


def _desired_settings() -> tuple[str, str]:
    scope = current_scope()
    if scope is None:
        return ("on", "")  # explicit platform bypass
    if scope is _UNSET:
        return ("off", "")  # no scope: policies match nothing
    return ("off", str(scope))


@event.listens_for(Pool, "connect")
def _probe_app_role(dbapi_connection, connection_record):
    role = _app_role()
    if not role or not hasattr(dbapi_connection, "get_backend_pid"):  # psycopg2 only, never SQLite
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"SET LOCAL ROLE {role}")
        connection_record.info[_ROLE_OK_KEY] = True
    except Exception as exc:  # noqa: BLE001 — any failure means "stay as the owner"
        connection_record.info[_ROLE_OK_KEY] = False
        logger.error("Cannot switch to APP_DB_ROLE %r (%s); running as the connecting role, RLS not applied", role, exc)
    finally:
        cursor.close()
        dbapi_connection.rollback()


@event.listens_for(Engine, "before_cursor_execute")
def _apply_scope(conn, cursor, statement, parameters, context, executemany):
    if conn.dialect.name != "postgresql":
        return
    desired = _desired_settings()
    applied = conn.info.get(_STATE_KEY)
    if applied == desired:
        return
    # A separate raw DB-API cursor: no SQLAlchemy events fire for it, so no
    # recursion, and the main statement's cursor is left untouched.
    raw = cursor.connection.cursor()
    try:
        if applied is None and conn.info.get(_ROLE_OK_KEY):
            # First statement of this transaction: drop to the restricted role.
            raw.execute(f"SET LOCAL ROLE {_app_role()}")
        raw.execute(
            "SELECT set_config('app.bypass', %s, true), set_config('app.company_id', %s, true)",
            desired,
        )
    finally:
        raw.close()
    conn.info[_STATE_KEY] = desired


@event.listens_for(Engine, "commit")
def _forget_on_commit(conn):
    conn.info.pop(_STATE_KEY, None)


@event.listens_for(Engine, "rollback")
def _forget_on_rollback(conn):
    conn.info.pop(_STATE_KEY, None)


@event.listens_for(Engine, "rollback_savepoint")
def _forget_on_savepoint_rollback(conn, name, context):
    conn.info.pop(_STATE_KEY, None)


@event.listens_for(Pool, "checkout")
def _forget_on_checkout(dbapi_connection, connection_record, connection_proxy):
    connection_record.info.pop(_STATE_KEY, None)
