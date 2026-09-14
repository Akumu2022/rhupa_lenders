"""M13/M14/M17: multi-stage loan approval chain, delegated limits, and the
expense ledger — CLAUDE.md §26, §28, §30.

- loanapplication.branch_id (nullable FK) + two new applicationstatus enum
  members (pending_branch_review, pending_committee_review).
- New applicationreviewstage table (append-only per-stage decision trail).
- New expenseentry table (cashier/finance officer's expense ledger).
- branch.delegated_limit (nullable override) and
  loanproduct.branch_manager_delegated_limit (required, DEV placeholder
  default) for the effective-limit computation (§26).

Revision ID: 56434f9ec315
Revises: 35bfe1df96dc
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '56434f9ec315'
down_revision: Union[str, Sequence[str], None] = '35bfe1df96dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- loanapplication.branch_id + new applicationstatus enum members ---
    # Postgres: 'applicationstatus' is a native enum type there — the two new
    # members MUST be added (and committed, via autocommit_block) before any
    # row/insert can use them. No data backfill happens in this migration
    # (existing 'pending' rows are left as historical data; only new
    # submissions use the new initial statuses going forward), so unlike
    # a4c8f1e6b930 there's no internal ordering hazard here — but the same
    # autocommit_block partial-commit lesson still applies to *retries*, so
    # every step below is guarded to be safe to re-run from a partial state.
    if bind.dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'pending_branch_review'")
            op.execute("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'pending_committee_review'")

    application_columns = {c['name'] for c in inspector.get_columns('loanapplication')}
    if 'branch_id' not in application_columns:
        with op.batch_alter_table('loanapplication') as batch_op:
            batch_op.add_column(sa.Column('branch_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_loanapplication_branch_id', 'branch', ['branch_id'], ['id'])
        op.create_index(
            op.f('ix_loanapplication_branch_id'), 'loanapplication', ['branch_id'], unique=False
        )

    # --- branch.delegated_limit ---
    branch_columns = {c['name'] for c in inspector.get_columns('branch')}
    if 'delegated_limit' not in branch_columns:
        with op.batch_alter_table('branch') as batch_op:
            batch_op.add_column(sa.Column('delegated_limit', sa.Numeric(precision=12, scale=2), nullable=True))

    # --- loanproduct.branch_manager_delegated_limit ---
    loanproduct_columns = {c['name'] for c in inspector.get_columns('loanproduct')}
    if 'branch_manager_delegated_limit' not in loanproduct_columns:
        with op.batch_alter_table('loanproduct') as batch_op:
            batch_op.add_column(
                sa.Column(
                    'branch_manager_delegated_limit',
                    sa.Numeric(precision=12, scale=2),
                    nullable=False,
                    server_default='100000.00',
                )
            )

    # --- applicationreviewstage (new table) ---
    if 'applicationreviewstage' not in inspector.get_table_names():
        op.create_table(
            'applicationreviewstage',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=True),
            sa.Column('application_id', sa.Integer(), nullable=False),
            sa.Column('stage', sa.Enum('branch_review', 'committee_review', name='reviewstage'), nullable=False),
            sa.Column('actor_id', sa.Integer(), nullable=False),
            sa.Column(
                'decision',
                sa.Enum('approve', 'reject', 'escalate', name='reviewdecision'),
                nullable=False,
            ),
            sa.Column('comments', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('decided_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['application_id'], ['loanapplication.id']),
            sa.ForeignKeyConstraint(['actor_id'], ['user.id']),
            sa.ForeignKeyConstraint(['company_id'], ['company.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(
            op.f('ix_applicationreviewstage_company_id'), 'applicationreviewstage', ['company_id'], unique=False
        )
        op.create_index(
            op.f('ix_applicationreviewstage_application_id'),
            'applicationreviewstage',
            ['application_id'],
            unique=False,
        )
        op.create_index(
            op.f('ix_applicationreviewstage_actor_id'), 'applicationreviewstage', ['actor_id'], unique=False
        )

    # --- expenseentry (new table) ---
    if 'expenseentry' not in inspector.get_table_names():
        op.create_table(
            'expenseentry',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=True),
            sa.Column('branch_id', sa.Integer(), nullable=True),
            sa.Column(
                'category',
                sa.Enum(
                    'salaries', 'rent', 'transport', 'communications', 'administration', 'other',
                    name='expensecategory',
                ),
                nullable=False,
            ),
            sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['branch_id'], ['branch.id']),
            sa.ForeignKeyConstraint(['created_by'], ['user.id']),
            sa.ForeignKeyConstraint(['company_id'], ['company.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_expenseentry_company_id'), 'expenseentry', ['company_id'], unique=False)
        op.create_index(op.f('ix_expenseentry_branch_id'), 'expenseentry', ['branch_id'], unique=False)
        op.create_index(op.f('ix_expenseentry_created_at'), 'expenseentry', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    op.drop_index(op.f('ix_expenseentry_created_at'), table_name='expenseentry')
    op.drop_index(op.f('ix_expenseentry_branch_id'), table_name='expenseentry')
    op.drop_index(op.f('ix_expenseentry_company_id'), table_name='expenseentry')
    op.drop_table('expenseentry')
    if bind.dialect.name == 'postgresql':
        sa.Enum(name='expensecategory').drop(bind, checkfirst=True)

    op.drop_index(op.f('ix_applicationreviewstage_actor_id'), table_name='applicationreviewstage')
    op.drop_index(op.f('ix_applicationreviewstage_application_id'), table_name='applicationreviewstage')
    op.drop_index(op.f('ix_applicationreviewstage_company_id'), table_name='applicationreviewstage')
    op.drop_table('applicationreviewstage')
    if bind.dialect.name == 'postgresql':
        sa.Enum(name='reviewdecision').drop(bind, checkfirst=True)
        sa.Enum(name='reviewstage').drop(bind, checkfirst=True)

    with op.batch_alter_table('loanproduct') as batch_op:
        batch_op.drop_column('branch_manager_delegated_limit')

    with op.batch_alter_table('branch') as batch_op:
        batch_op.drop_column('delegated_limit')

    op.drop_index(op.f('ix_loanapplication_branch_id'), table_name='loanapplication')
    with op.batch_alter_table('loanapplication') as batch_op:
        batch_op.drop_constraint('fk_loanapplication_branch_id', type_='foreignkey')
        batch_op.drop_column('branch_id')

    # applicationstatus's new enum members are left in place — Postgres enum
    # values can't be dropped without recreating the type, same precedent as
    # every earlier ADD VALUE migration in this history.
