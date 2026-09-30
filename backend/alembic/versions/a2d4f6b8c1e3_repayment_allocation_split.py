"""Repayment allocation: penalties -> interest -> principal.

Adds running repaid totals per component on Loan, and the per-payment split
on Transaction.

Backfill for existing loans, from what was actually recorded:
- Earlier payments filled schedule instalments (principal + base interest)
  in order and never allocated anything to penalties. Within each
  instalment the paid amount is read as interest first, then principal
  (the same rule going forward).
- Anything repaid beyond what reached the schedule went to penalties:
  penalties_repaid = total repaid - sum(instalment amount_paid).
Existing repayment Transaction rows keep a NULL split: how each historical
payment divided up was never recorded and is not reconstructed.

Revision ID: a2d4f6b8c1e3
Revises: f1c7d3a9e2b5
Create Date: 2026-09-30 15:00:00.000000

"""
from decimal import Decimal
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a2d4f6b8c1e3'
down_revision: Union[str, Sequence[str], None] = 'f1c7d3a9e2b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ZERO = Decimal("0.00")
_MONEY = sa.Numeric(12, 2)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    loan_columns = {c['name'] for c in inspector.get_columns('loan')}
    if 'principal_repaid' not in loan_columns:
        with op.batch_alter_table('loan') as batch_op:
            for name in ('principal_repaid', 'interest_repaid', 'penalties_repaid'):
                batch_op.add_column(sa.Column(name, _MONEY, nullable=False, server_default='0'))

    txn_columns = {c['name'] for c in inspector.get_columns('transaction')}
    if 'principal_portion' not in txn_columns:
        with op.batch_alter_table('transaction') as batch_op:
            for name in ('penalty_portion', 'interest_portion', 'principal_portion'):
                batch_op.add_column(sa.Column(name, _MONEY, nullable=True))

    loans = bind.execute(
        sa.text("SELECT id, principal, total_repayable, penalties_accrued, outstanding_balance FROM loan")
    ).fetchall()
    for loan_id, principal, total_repayable, penalties_accrued, outstanding in loans:
        principal, total_repayable = Decimal(principal), Decimal(total_repayable)
        penalties_accrued, outstanding = Decimal(penalties_accrued), Decimal(outstanding)
        installments = bind.execute(
            sa.text("SELECT amount_paid, interest_component FROM repaymentschedule WHERE loan_id = :id"),
            {"id": loan_id},
        ).fetchall()
        paid_to_schedule = sum((Decimal(p) for p, _ in installments), _ZERO)
        interest_repaid = sum((min(Decimal(p), Decimal(i)) for p, i in installments), _ZERO)
        principal_repaid = min(paid_to_schedule - interest_repaid, principal)
        # Loans created before instalments carried an interest/principal
        # split have interest_component = 0; whatever reached the schedule
        # beyond the principal was interest.
        leftover = paid_to_schedule - interest_repaid - principal_repaid
        interest_repaid = min(interest_repaid + leftover, total_repayable - principal)
        total_repaid = max(total_repayable + penalties_accrued - outstanding, _ZERO)
        penalties_repaid = min(max(total_repaid - paid_to_schedule, _ZERO), penalties_accrued)
        bind.execute(
            sa.text(
                "UPDATE loan SET principal_repaid = :p, interest_repaid = :i, penalties_repaid = :pen WHERE id = :id"
            ),
            # Exact decimal strings: sqlite3 can't bind Decimal, and a float
            # would lose cents. Postgres casts the string to NUMERIC exactly.
            {
                "p": str(principal_repaid.quantize(Decimal("0.01"))),
                "i": str(interest_repaid.quantize(Decimal("0.01"))),
                "pen": str(penalties_repaid.quantize(Decimal("0.01"))),
                "id": loan_id,
            },
        )


def downgrade() -> None:
    with op.batch_alter_table('transaction') as batch_op:
        for name in ('principal_portion', 'interest_portion', 'penalty_portion'):
            batch_op.drop_column(name)
    with op.batch_alter_table('loan') as batch_op:
        for name in ('penalties_repaid', 'interest_repaid', 'principal_repaid'):
            batch_op.drop_column(name)
