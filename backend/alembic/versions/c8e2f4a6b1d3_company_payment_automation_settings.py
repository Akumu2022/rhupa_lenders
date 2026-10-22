"""Company payment-automation settings: auto-disburse and STK push (all off).

Revision ID: c8e2f4a6b1d3
Revises: b7d1e3f5a9c2
Create Date: 2026-10-22 00:00:01.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c8e2f4a6b1d3'
down_revision: Union[str, Sequence[str], None] = 'b7d1e3f5a9c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('company', sa.Column('auto_disburse_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('company', sa.Column('auto_disburse_max_amount', sa.Numeric(12, 2), nullable=True))
    op.add_column('company', sa.Column('stk_push_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('company', 'stk_push_enabled')
    op.drop_column('company', 'auto_disburse_max_amount')
    op.drop_column('company', 'auto_disburse_enabled')
