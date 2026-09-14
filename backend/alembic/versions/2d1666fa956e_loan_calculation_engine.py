"""CLAUDE.md §23: loan calculation engine — interest model + penalty config
on LoanProduct, penalty accrual tracking on Loan, and a 'penalty' Transaction
type.

Revision ID: 2d1666fa956e
Revises: b2a6aaba7d2e
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '2d1666fa956e'
down_revision: Union[str, Sequence[str], None] = 'b2a6aaba7d2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Every existing product becomes an explicit 'flat' product with the DEV
    # placeholder penalty config (CLAUDE.md §23) — behaviorally identical to
    # today (flat, single installment, no accrual yet since nothing is overdue
    # until the next due-date scan finds it).
    with op.batch_alter_table('loanproduct') as batch_op:
        batch_op.add_column(
            sa.Column('interest_model', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='flat')
        )
        batch_op.add_column(sa.Column('installment_count', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(
            sa.Column(
                'penalty_type',
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default='percentage_per_day',
            )
        )
        batch_op.add_column(
            sa.Column('penalty_rate', sa.Numeric(precision=5, scale=2), nullable=False, server_default='1.00')
        )
        batch_op.add_column(sa.Column('grace_period_days', sa.Integer(), nullable=False, server_default='3'))
        batch_op.add_column(
            sa.Column('penalty_cap_ratio', sa.Numeric(precision=5, scale=2), nullable=False, server_default='1.00')
        )

    with op.batch_alter_table('loan') as batch_op:
        batch_op.add_column(
            sa.Column('penalties_accrued', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0')
        )
        batch_op.add_column(sa.Column('last_penalty_check_date', sa.Date(), nullable=True))

    # Postgres: the 'transactiontype' column is a native enum type there, so a
    # new member needs an explicit ALTER TYPE (outside the migration's
    # transaction — Postgres cannot add an enum value and use it in the same
    # transaction on older versions). SQLite has no native enum — the column
    # is a plain VARCHAR with no CHECK constraint, so there is nothing to do.
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'penalty'")


def downgrade() -> None:
    """Downgrade schema.

    Postgres enum values cannot be dropped without recreating the type; left
    in place on downgrade (an unused 'penalty' member is harmless).
    """
    with op.batch_alter_table('loan') as batch_op:
        batch_op.drop_column('last_penalty_check_date')
        batch_op.drop_column('penalties_accrued')

    with op.batch_alter_table('loanproduct') as batch_op:
        batch_op.drop_column('penalty_cap_ratio')
        batch_op.drop_column('grace_period_days')
        batch_op.drop_column('penalty_rate')
        batch_op.drop_column('penalty_type')
        batch_op.drop_column('installment_count')
        batch_op.drop_column('interest_model')
