"""M12: guarantors and collateral (securities) — CLAUDE.md §27.

- New guarantor table (per-application, verification_status enum).
- New security table (per-application collateral).
- loanproduct.requires_guarantor (bool, default false).

Revision ID: a1f6c9d2e4b7
Revises: 56434f9ec315
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a1f6c9d2e4b7'
down_revision: Union[str, Sequence[str], None] = '56434f9ec315'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- loanproduct.requires_guarantor ---
    loanproduct_columns = {c['name'] for c in inspector.get_columns('loanproduct')}
    if 'requires_guarantor' not in loanproduct_columns:
        with op.batch_alter_table('loanproduct') as batch_op:
            batch_op.add_column(
                sa.Column('requires_guarantor', sa.Boolean(), nullable=False, server_default=sa.false())
            )

    # --- guarantor (new table) ---
    if 'guarantor' not in inspector.get_table_names():
        op.create_table(
            'guarantor',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=True),
            sa.Column('application_id', sa.Integer(), nullable=False),
            sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('id_number', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('phone_number', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('occupation', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('residence', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('relationship', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('guaranteed_amount', sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column('consent', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                'verification_status',
                sa.Enum('pending', 'verified', 'rejected', name='guarantorverificationstatus'),
                nullable=False,
                server_default='pending',
            ),
            sa.Column('verified_by', sa.Integer(), nullable=True),
            sa.Column('verified_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['application_id'], ['loanapplication.id']),
            sa.ForeignKeyConstraint(['verified_by'], ['user.id']),
            sa.ForeignKeyConstraint(['company_id'], ['company.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_guarantor_company_id'), 'guarantor', ['company_id'], unique=False)
        op.create_index(op.f('ix_guarantor_application_id'), 'guarantor', ['application_id'], unique=False)
        op.create_index(op.f('ix_guarantor_created_at'), 'guarantor', ['created_at'], unique=False)

    # --- security (new table) ---
    if 'security' not in inspector.get_table_names():
        op.create_table(
            'security',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=True),
            sa.Column('application_id', sa.Integer(), nullable=False),
            sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('estimated_value', sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column('document_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['application_id'], ['loanapplication.id']),
            sa.ForeignKeyConstraint(['company_id'], ['company.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_security_company_id'), 'security', ['company_id'], unique=False)
        op.create_index(op.f('ix_security_application_id'), 'security', ['application_id'], unique=False)
        op.create_index(op.f('ix_security_created_at'), 'security', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    op.drop_index(op.f('ix_security_created_at'), table_name='security')
    op.drop_index(op.f('ix_security_application_id'), table_name='security')
    op.drop_index(op.f('ix_security_company_id'), table_name='security')
    op.drop_table('security')

    op.drop_index(op.f('ix_guarantor_created_at'), table_name='guarantor')
    op.drop_index(op.f('ix_guarantor_application_id'), table_name='guarantor')
    op.drop_index(op.f('ix_guarantor_company_id'), table_name='guarantor')
    op.drop_table('guarantor')
    if bind.dialect.name == 'postgresql':
        sa.Enum(name='guarantorverificationstatus').drop(bind, checkfirst=True)

    with op.batch_alter_table('loanproduct') as batch_op:
        batch_op.drop_column('requires_guarantor')
