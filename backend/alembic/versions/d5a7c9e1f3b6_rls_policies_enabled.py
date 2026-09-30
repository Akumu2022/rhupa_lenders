"""Row-level security, stage 1: create the tenant policies (not forced).

Every tenant-owned table gets ENABLE ROW LEVEL SECURITY plus the
tenant_isolation policy (app/rls.py). This changes nothing in production
yet: the app's database role owns these tables and Postgres exempts owners
until FORCE ROW LEVEL SECURITY is set, which is the separate stage-2
migration. Postgres only; a no-op on SQLite.

The table list and predicate are copied (not imported) so this migration
keeps meaning the same thing even if app/rls.py changes later.

Revision ID: d5a7c9e1f3b6
Revises: c4f6b8d0e2a5
Create Date: 2026-09-30 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd5a7c9e1f3b6'
down_revision: Union[str, Sequence[str], None] = 'c4f6b8d0e2a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = (
    "applicationreviewstage", "auditlog", "branch", "businessassessment", "expenseentry", "guarantor",
    "loan", "loanapplication", "loanproduct", "mfarecoverycode", "profile", "referee",
    "repaymentschedule", "security", "transaction", "user",
)
PREDICATE = (
    "current_setting('app.bypass', true) = 'on' "
    "OR company_id::text = current_setting('app.company_id', true)"
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'CREATE POLICY tenant_isolation ON "{table}" USING ({PREDICATE}) WITH CHECK ({PREDICATE})')


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
