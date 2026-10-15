"""Add 'written_off' to the Postgres loanstatus enum.

Revision ID: b7d1e3f5a9c2
Revises: a9c3e5f7b1d2
Create Date: 2026-10-15 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b7d1e3f5a9c2'
down_revision: Union[str, Sequence[str], None] = 'a9c3e5f7b1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE loanstatus ADD VALUE IF NOT EXISTS 'written_off'")


def downgrade() -> None:
    pass  # Postgres enum members cannot be dropped; unused member is harmless.
