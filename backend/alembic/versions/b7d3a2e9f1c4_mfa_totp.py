"""TOTP MFA for staff roles — CLAUDE.md §4.

- user.mfa_secret (nullable) and user.mfa_enabled (NOT NULL DEFAULT false).
- New mfarecoverycode table (single-use recovery codes, hashed at rest).

Revision ID: b7d3a2e9f1c4
Revises: a1f6c9d2e4b7
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b7d3a2e9f1c4'
down_revision: Union[str, Sequence[str], None] = 'a1f6c9d2e4b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_columns = {c['name'] for c in inspector.get_columns('user')}
    if 'mfa_secret' not in user_columns:
        with op.batch_alter_table('user') as batch_op:
            batch_op.add_column(sa.Column('mfa_secret', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    if 'mfa_enabled' not in user_columns:
        with op.batch_alter_table('user') as batch_op:
            batch_op.add_column(
                sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default=sa.false())
            )

    if 'mfarecoverycode' not in inspector.get_table_names():
        op.create_table(
            'mfarecoverycode',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('code_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['user.id']),
            sa.ForeignKeyConstraint(['company_id'], ['company.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_mfarecoverycode_company_id'), 'mfarecoverycode', ['company_id'], unique=False)
        op.create_index(op.f('ix_mfarecoverycode_user_id'), 'mfarecoverycode', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_mfarecoverycode_user_id'), table_name='mfarecoverycode')
    op.drop_index(op.f('ix_mfarecoverycode_company_id'), table_name='mfarecoverycode')
    op.drop_table('mfarecoverycode')

    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('mfa_enabled')
        batch_op.drop_column('mfa_secret')
