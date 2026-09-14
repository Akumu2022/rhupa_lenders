"""M10: Branch entity + role rename (company_admin -> system_administrator,
compliance_officer retired/merged into credit_officer) — CLAUDE.md §3, §25.

Revision ID: a4c8f1e6b930
Revises: 2d1666fa956e
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a4c8f1e6b930'
down_revision: Union[str, Sequence[str], None] = '2d1666fa956e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'branch',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('code', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('address', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('manager_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['company.id']),
        sa.ForeignKeyConstraint(['manager_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        # CLAUDE.md §25: code is unique per company, not globally — two
        # different companies may each have their own "HQ" branch.
        sa.UniqueConstraint('company_id', 'code', name='uq_branch_company_code'),
    )
    op.create_index(op.f('ix_branch_company_id'), 'branch', ['company_id'], unique=False)
    op.create_index(op.f('ix_branch_code'), 'branch', ['code'], unique=False)

    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_user_branch_id', 'branch', ['branch_id'], ['id'])
    op.create_index(op.f('ix_user_branch_id'), 'user', ['branch_id'], unique=False)

    # CLAUDE.md §3: company_admin -> system_administrator; compliance_officer
    # retired (credit_officer absorbs KYC). Remap existing rows so dev.db (and
    # any already-deployed data) isn't left with orphaned role strings.
    op.execute("UPDATE \"user\" SET role = 'system_administrator' WHERE role = 'company_admin'")
    op.execute("UPDATE \"user\" SET role = 'credit_officer' WHERE role = 'compliance_officer'")

    # Postgres: 'userrole' is a native enum type there, so the new members
    # need an explicit ALTER TYPE (outside the migration's transaction — same
    # pattern as the 'transactiontype' change in 2d1666fa956e). SQLite has no
    # native enum — the column is a plain VARCHAR with no CHECK constraint, so
    # there is nothing to do beyond the data UPDATE above. The retired
    # 'company_admin'/'compliance_officer' values are left in the Postgres
    # enum type (unused, harmless) since they can't be dropped without
    # recreating the type — same precedent as that migration's downgrade note.
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            for new_role in (
                'system_administrator',
                'branch_manager',
                'loan_vetting_committee',
                'cashier_finance_officer',
                'management',
            ):
                op.execute(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{new_role}'")


def downgrade() -> None:
    """Downgrade schema.

    NOTE: compliance_officer -> credit_officer was a genuine merge (§3) —
    which credit_officer rows were originally compliance_officer is not
    recoverable from data alone. This downgrade does NOT attempt to split
    them back apart; it only reverses the additive schema changes
    (Branch table, User.branch_id) and the unambiguous system_administrator
    rename. Restoring a true pre-M10 role split requires a backup.
    """
    op.execute("UPDATE \"user\" SET role = 'company_admin' WHERE role = 'system_administrator'")

    op.drop_index(op.f('ix_user_branch_id'), table_name='user')
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_constraint('fk_user_branch_id', type_='foreignkey')
        batch_op.drop_column('branch_id')

    op.drop_index(op.f('ix_branch_code'), table_name='branch')
    op.drop_index(op.f('ix_branch_company_id'), table_name='branch')
    op.drop_table('branch')
