"""M9: loan delinquency stage, amortization breakdown, company branding

Revision ID: b2a6aaba7d2e
Revises: d2e20d38c738
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b2a6aaba7d2e'
down_revision: Union[str, Sequence[str], None] = 'd2e20d38c738'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # LoanStatus gains 'overdue' and 'defaulted' (CLAUDE.md §19). SQLite never
    # enforces VARCHAR(n) length so this is a no-op there, but Postgres does —
    # the original column was sized to 'approved' (8 chars); 'defaulted' is 9.
    with op.batch_alter_table('loan') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.String(length=8),
            type_=sa.String(length=20),
            existing_nullable=False,
        )

    # Amortization breakdown (CLAUDE.md §19 borrower transparency): backfill
    # existing rows to principal-only (interest_component=0) — the exact split
    # is only meaningful going forward for schedules the app itself generates.
    with op.batch_alter_table('repaymentschedule') as batch_op:
        batch_op.add_column(
            sa.Column(
                'principal_component',
                sa.Numeric(precision=12, scale=2),
                nullable=False,
                server_default='0',
            )
        )
        batch_op.add_column(
            sa.Column(
                'interest_component',
                sa.Numeric(precision=12, scale=2),
                nullable=False,
                server_default='0',
            )
        )
    op.execute('UPDATE repaymentschedule SET principal_component = amount_due')

    # Company profile + branding (CLAUDE.md §21) — all optional/nullable, so
    # existing companies simply fall back to platform defaults until edited.
    with op.batch_alter_table('company') as batch_op:
        batch_op.add_column(sa.Column('legal_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('tagline', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('logo_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('brand_primary_color', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('brand_accent_color', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('support_email', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('support_phone', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('address', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('registration_number', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('company') as batch_op:
        batch_op.drop_column('registration_number')
        batch_op.drop_column('address')
        batch_op.drop_column('support_phone')
        batch_op.drop_column('support_email')
        batch_op.drop_column('brand_accent_color')
        batch_op.drop_column('brand_primary_color')
        batch_op.drop_column('logo_url')
        batch_op.drop_column('tagline')
        batch_op.drop_column('legal_name')

    with op.batch_alter_table('repaymentschedule') as batch_op:
        batch_op.drop_column('interest_component')
        batch_op.drop_column('principal_component')

    with op.batch_alter_table('loan') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.String(length=20),
            type_=sa.String(length=8),
            existing_nullable=False,
        )
