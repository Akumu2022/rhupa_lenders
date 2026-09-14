"""M11: extended customer registration fields, customer_number sequence,
Referee and BusinessAssessment tables — CLAUDE.md §27.

Revision ID: f7b3d9a2c815
Revises: a4c8f1e6b930
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f7b3d9a2c815'
down_revision: Union[str, Sequence[str], None] = 'a4c8f1e6b930'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # CLAUDE.md §27: every new Profile column is nullable — the self-signup
    # /profile submission (M2) keeps working unchanged; only the new
    # credit-officer registration endpoint requires the fuller set, at its
    # own Pydantic layer, not here.
    with op.batch_alter_table('profile') as batch_op:
        batch_op.add_column(sa.Column('first_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('middle_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('last_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('id_type', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('gender', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('nationality', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('marital_status', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('dependants_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('phone_number_alt', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('next_of_kin_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('next_of_kin_relationship', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('next_of_kin_phone', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('customer_number', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_index(op.f('ix_profile_customer_number'), 'profile', ['customer_number'], unique=False)

    with op.batch_alter_table('company') as batch_op:
        batch_op.add_column(
            sa.Column('next_customer_sequence', sa.Integer(), nullable=False, server_default='1')
        )

    op.create_table(
        'referee',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('phone_number', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('relationship', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('address', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['company.id']),
        sa.ForeignKeyConstraint(['profile_id'], ['profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_referee_company_id'), 'referee', ['company_id'], unique=False)
    op.create_index(op.f('ix_referee_profile_id'), 'referee', ['profile_id'], unique=False)

    op.create_table(
        'businessassessment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('business_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('business_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('ownership', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('physical_location', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('years_in_operation', sa.Integer(), nullable=False),
        sa.Column('sales_frequency', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('total_income', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('total_expenses', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('reported_profit', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('stock_value', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('existing_loans_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('other_lenders', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('bank_mpesa_turnover', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('business_assets_value', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('cash_flow_notes', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('existing_debt_obligations', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('net_income', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('debt_service_capacity', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['company.id']),
        sa.ForeignKeyConstraint(['created_by'], ['user.id']),
        sa.ForeignKeyConstraint(['profile_id'], ['profile.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile_id', name='uq_businessassessment_profile_id'),
    )
    op.create_index(op.f('ix_businessassessment_company_id'), 'businessassessment', ['company_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_businessassessment_company_id'), table_name='businessassessment')
    op.drop_table('businessassessment')

    op.drop_index(op.f('ix_referee_profile_id'), table_name='referee')
    op.drop_index(op.f('ix_referee_company_id'), table_name='referee')
    op.drop_table('referee')

    with op.batch_alter_table('company') as batch_op:
        batch_op.drop_column('next_customer_sequence')

    op.drop_index(op.f('ix_profile_customer_number'), table_name='profile')
    with op.batch_alter_table('profile') as batch_op:
        batch_op.drop_column('customer_number')
        batch_op.drop_column('next_of_kin_phone')
        batch_op.drop_column('next_of_kin_relationship')
        batch_op.drop_column('next_of_kin_name')
        batch_op.drop_column('phone_number_alt')
        batch_op.drop_column('dependants_count')
        batch_op.drop_column('marital_status')
        batch_op.drop_column('nationality')
        batch_op.drop_column('gender')
        batch_op.drop_column('id_type')
        batch_op.drop_column('last_name')
        batch_op.drop_column('middle_name')
        batch_op.drop_column('first_name')
