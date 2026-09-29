"""Add company.created_at — CLAUDE.md §21/platform company-detail view.

Existing rows get the migration's own timestamp (via server_default now()),
not their true original creation date, which was never captured before this
change — there is no way to recover it retroactively.

Revision ID: c9e1f4a6b8d2
Revises: b7d3a2e9f1c4
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e1f4a6b8d2'
down_revision: Union[str, Sequence[str], None] = 'b7d3a2e9f1c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    company_columns = {c['name'] for c in inspector.get_columns('company')}
    if 'created_at' not in company_columns:
        with op.batch_alter_table('company') as batch_op:
            batch_op.add_column(
                sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
            )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('company') as batch_op:
        batch_op.drop_column('created_at')
