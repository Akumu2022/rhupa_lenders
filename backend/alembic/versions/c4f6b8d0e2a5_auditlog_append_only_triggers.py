"""Make auditlog append-only at the database level.

CLAUDE.md §12 requires that audit history can't be rewritten even by a bug.
Revoking UPDATE/DELETE grants doesn't bind the table owner (the app's role
on Neon), so triggers that reject UPDATE, DELETE and TRUNCATE are used
instead; they apply to every role, owner included.

The statements mirror app/models/audit_log.py (AUDIT_APPEND_ONLY_*), which
installs the same triggers on create_all; this migration covers databases
that already exist.

Revision ID: c4f6b8d0e2a5
Revises: b3e5a7c9d2f4
Create Date: 2026-09-30 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c4f6b8d0e2a5'
down_revision: Union[str, Sequence[str], None] = 'b3e5a7c9d2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQLITE = [
    "CREATE TRIGGER IF NOT EXISTS auditlog_no_update BEFORE UPDATE ON auditlog "
    "BEGIN SELECT RAISE(ABORT, 'auditlog is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS auditlog_no_delete BEFORE DELETE ON auditlog "
    "BEGIN SELECT RAISE(ABORT, 'auditlog is append-only'); END",
]
_POSTGRES = [
    "CREATE OR REPLACE FUNCTION auditlog_append_only() RETURNS trigger AS $$ "
    "BEGIN RAISE EXCEPTION 'auditlog is append-only'; END; $$ LANGUAGE plpgsql",
    "DROP TRIGGER IF EXISTS auditlog_no_update_delete ON auditlog",
    "CREATE TRIGGER auditlog_no_update_delete BEFORE UPDATE OR DELETE ON auditlog "
    "FOR EACH ROW EXECUTE FUNCTION auditlog_append_only()",
    "DROP TRIGGER IF EXISTS auditlog_no_truncate ON auditlog",
    "CREATE TRIGGER auditlog_no_truncate BEFORE TRUNCATE ON auditlog "
    "FOR EACH STATEMENT EXECUTE FUNCTION auditlog_append_only()",
]


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    for statement in _POSTGRES if dialect == "postgresql" else _SQLITE if dialect == "sqlite" else []:
        op.execute(statement)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS auditlog_no_truncate ON auditlog")
        op.execute("DROP TRIGGER IF EXISTS auditlog_no_update_delete ON auditlog")
        op.execute("DROP FUNCTION IF EXISTS auditlog_append_only()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS auditlog_no_delete")
        op.execute("DROP TRIGGER IF EXISTS auditlog_no_update")
