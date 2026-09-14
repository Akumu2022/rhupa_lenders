"""Fix loanproduct.interest_model/penalty_type: create the missing Postgres
native enum types and convert the columns to them.

2d1666fa956e added these two columns as plain VARCHAR
(sqlmodel.sql.sqltypes.AutoString()), but app/models/loan_product.py
declares them as native Python enums (InterestModel/PenaltyType), which
SQLAlchemy/SQLModel maps to native Postgres ENUM columns bound to types
named 'interestmodel' and 'penaltytype' — types that were never actually
created by any migration. SQLite has no native enum concept, so a VARCHAR
column works there regardless of what the model declares, and the app's
test suite builds its schema via SQLModel.metadata.create_all (which reads
the live model, not migrations) — so this mismatch was invisible until the
first real INSERT against Postgres (company creation, which seeds three
LoanProduct rows) failed with
psycopg2.errors.UndefinedObject: type "interestmodel" does not exist.

Revision ID: 04f0ffdd1b2f
Revises: c3e7a815f204
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04f0ffdd1b2f'
down_revision: Union[str, Sequence[str], None] = 'c3e7a815f204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

interest_model_enum = sa.Enum('flat', 'reducing_balance', 'daily_accrual', name='interestmodel')
penalty_type_enum = sa.Enum('percentage_per_day', name='penaltytype')


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        # SQLite has no native enum type — the existing VARCHAR column
        # already behaves correctly there. Nothing to do.
        return

    interest_model_enum.create(bind, checkfirst=True)
    penalty_type_enum.create(bind, checkfirst=True)

    # DROP DEFAULT first — Postgres can't always auto-cast an existing
    # text-typed default expression across a column type change.
    op.execute('ALTER TABLE loanproduct ALTER COLUMN interest_model DROP DEFAULT')
    op.execute(
        'ALTER TABLE loanproduct ALTER COLUMN interest_model TYPE interestmodel '
        'USING interest_model::interestmodel'
    )
    op.execute("ALTER TABLE loanproduct ALTER COLUMN interest_model SET DEFAULT 'flat'::interestmodel")

    op.execute('ALTER TABLE loanproduct ALTER COLUMN penalty_type DROP DEFAULT')
    op.execute(
        'ALTER TABLE loanproduct ALTER COLUMN penalty_type TYPE penaltytype '
        'USING penalty_type::penaltytype'
    )
    op.execute("ALTER TABLE loanproduct ALTER COLUMN penalty_type SET DEFAULT 'percentage_per_day'::penaltytype")


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    op.execute('ALTER TABLE loanproduct ALTER COLUMN interest_model DROP DEFAULT')
    op.execute('ALTER TABLE loanproduct ALTER COLUMN interest_model TYPE VARCHAR USING interest_model::text')
    op.execute("ALTER TABLE loanproduct ALTER COLUMN interest_model SET DEFAULT 'flat'")

    op.execute('ALTER TABLE loanproduct ALTER COLUMN penalty_type DROP DEFAULT')
    op.execute('ALTER TABLE loanproduct ALTER COLUMN penalty_type TYPE VARCHAR USING penalty_type::text')
    op.execute("ALTER TABLE loanproduct ALTER COLUMN penalty_type SET DEFAULT 'percentage_per_day'")

    interest_model_enum.drop(bind, checkfirst=True)
    penalty_type_enum.drop(bind, checkfirst=True)
