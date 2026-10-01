"""Let the owner switch to the restricted app role (SET ROLE rhupa_app).

The app connects with the owner's URL and drops to rhupa_app at the start of
every transaction (app/rls.py, APP_DB_ROLE), so row-level security applies
to it. That needs membership with the SET option. No-op where the role does
not exist (SQLite, CI, fresh databases) and harmless to re-run. Never fails
the deploy: if the grant is refused, the app's on-connect probe notices and
keeps running as the owner.

Revision ID: a9c3e5f7b1d2
Revises: d5a7c9e1f3b6
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a9c3e5f7b1d2'
down_revision: Union[str, Sequence[str], None] = 'd5a7c9e1f3b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GRANT = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rhupa_app') THEN
    BEGIN
      EXECUTE format('GRANT rhupa_app TO %I WITH SET TRUE, INHERIT FALSE', current_user);
    EXCEPTION WHEN syntax_error THEN
      -- Postgres 15 and older: no per-membership options.
      EXECUTE format('GRANT rhupa_app TO %I', current_user);
    END;
  END IF;
EXCEPTION WHEN OTHERS THEN
  RAISE WARNING 'Could not grant rhupa_app to %: %', current_user, SQLERRM;
END
$$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(GRANT)


def downgrade() -> None:
    pass
