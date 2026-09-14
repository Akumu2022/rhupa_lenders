"""Performance indexes (senior-engineer review): composite index on
RepaymentSchedule(is_paid, due_date) backing app/loan_delinquency.py's
hot-path query, and created_at indexes on LoanApplication/Loan/AuditLog
backing every oversight/queue ORDER BY.

Revision ID: c3e7a815f204
Revises: f7b3d9a2c815
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3e7a815f204'
down_revision: Union[str, Sequence[str], None] = 'f7b3d9a2c815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'ix_repaymentschedule_is_paid_due_date', 'repaymentschedule', ['is_paid', 'due_date'], unique=False
    )
    op.create_index(op.f('ix_loanapplication_created_at'), 'loanapplication', ['created_at'], unique=False)
    op.create_index(op.f('ix_loan_created_at'), 'loan', ['created_at'], unique=False)
    op.create_index(op.f('ix_auditlog_created_at'), 'auditlog', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_auditlog_created_at'), table_name='auditlog')
    op.drop_index(op.f('ix_loan_created_at'), table_name='loan')
    op.drop_index(op.f('ix_loanapplication_created_at'), table_name='loanapplication')
    op.drop_index('ix_repaymentschedule_is_paid_due_date', table_name='repaymentschedule')
