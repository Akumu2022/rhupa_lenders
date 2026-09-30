"""Add loanapplication.prepared_by — the credit officer who prepared an
officer-assisted application (drives per-officer portfolio views).

Backfilled from the existing `application.submit_for_customer` audit entries,
which already record the submitting officer as actor — so historical
officer-assisted applications get their true preparer, not a guess.
Self-service applications stay null.

Revision ID: e4a8c2f9b1d7
Revises: c9e1f4a6b8d2
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4a8c2f9b1d7'
down_revision: Union[str, Sequence[str], None] = 'c9e1f4a6b8d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c['name'] for c in inspector.get_columns('loanapplication')}
    if 'prepared_by' not in columns:
        with op.batch_alter_table('loanapplication') as batch_op:
            batch_op.add_column(sa.Column('prepared_by', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_loanapplication_prepared_by_user', 'user', ['prepared_by'], ['id'])
            batch_op.create_index('ix_loanapplication_prepared_by', ['prepared_by'])

    op.execute(
        """
        UPDATE loanapplication
        SET prepared_by = (
            SELECT auditlog.actor_id FROM auditlog
            WHERE auditlog.entity_type = 'LoanApplication'
              AND auditlog.entity_id = loanapplication.id
              AND auditlog.action = 'application.submit_for_customer'
            ORDER BY auditlog.id LIMIT 1
        )
        WHERE prepared_by IS NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table('loanapplication') as batch_op:
        batch_op.drop_index('ix_loanapplication_prepared_by')
        batch_op.drop_constraint('fk_loanapplication_prepared_by_user', type_='foreignkey')
        batch_op.drop_column('prepared_by')
