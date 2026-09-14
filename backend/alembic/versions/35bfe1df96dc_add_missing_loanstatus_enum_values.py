"""Add the missing 'overdue'/'defaulted' members to the Postgres loanstatus
enum type.

ed31a40c97f5 created the 'loanstatus' native Postgres enum with only
('approved', 'active', 'repaid') — matching the loan ladder at the time.
app/models/loan.py's LoanStatus enum was later extended with 'overdue' and
'defaulted' (CLAUDE.md §19's delinquency ladder), but no migration ever
added those as members of the Postgres type. Same class of bug as
a4c8f1e6b930 (userrole) and 04f0ffdd1b2f (interestmodel/penaltytype):
invisible on SQLite, and would only surface the first time a loan
actually transitions to overdue or defaulted against a real Postgres
database — caught here proactively via the same audit that found those.

Revision ID: 35bfe1df96dc
Revises: 04f0ffdd1b2f
Create Date: 2026-09-14 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '35bfe1df96dc'
down_revision: Union[str, Sequence[str], None] = '04f0ffdd1b2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return  # SQLite has no native enum type — nothing to do.

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE loanstatus ADD VALUE IF NOT EXISTS 'overdue'")
        op.execute("ALTER TYPE loanstatus ADD VALUE IF NOT EXISTS 'defaulted'")


def downgrade() -> None:
    """Downgrade schema.

    Postgres enum values cannot be dropped without recreating the type;
    left in place on downgrade (unused members are harmless), matching the
    precedent in every earlier ADD VALUE migration in this history.
    """
    pass
