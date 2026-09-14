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
    """Upgrade schema.

    Every step below is guarded to be safe to re-run from a partial state.
    `autocommit_block()` (further down, for the Postgres ALTER TYPE calls)
    force-commits everything before it in this same function — even though
    Alembic hasn't yet recorded this migration as applied — so if anything
    after that point ever fails, a retry re-executes this whole upgrade()
    from the top against a database that already has some of it. Without
    guards, `CREATE TABLE branch` would then fail with "relation already
    exists" and mask whatever the real failure was.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'branch' not in inspector.get_table_names():
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

    user_columns = {c['name'] for c in inspector.get_columns('user')}
    if 'branch_id' not in user_columns:
        with op.batch_alter_table('user') as batch_op:
            batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_user_branch_id', 'branch', ['branch_id'], ['id'])
        op.create_index(op.f('ix_user_branch_id'), 'user', ['branch_id'], unique=False)

    # Postgres: 'userrole' is a native enum type there, so the new members
    # need an explicit ALTER TYPE (outside the migration's transaction — same
    # pattern as the 'transactiontype' change in 2d1666fa956e) — and it MUST
    # run before the data UPDATE below: Postgres validates a string literal
    # against the enum's current members at parse time, regardless of
    # whether any row matches the WHERE clause, so
    # `UPDATE ... SET role = 'system_administrator'` fails with DataError
    # ("invalid input value for enum userrole") on a fresh, even empty,
    # database until the type actually has that member. SQLite has no native
    # enum — the column is a plain VARCHAR with no CHECK constraint, so there
    # is nothing to do here. The retired 'company_admin'/'compliance_officer'
    # values are left in the Postgres enum type (unused, harmless) since they
    # can't be dropped without recreating the type — same precedent as that
    # migration's downgrade note.
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

    # CLAUDE.md §3: company_admin -> system_administrator; compliance_officer
    # retired (credit_officer absorbs KYC). Remap existing rows so dev.db (and
    # any already-deployed data) isn't left with orphaned role strings.
    op.execute("UPDATE \"user\" SET role = 'system_administrator' WHERE role = 'company_admin'")
    op.execute("UPDATE \"user\" SET role = 'credit_officer' WHERE role = 'compliance_officer'")


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
