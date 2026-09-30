"""Staff-recorded repayments: payment method/reference/receipt/recorder on
Transaction, plus a per-company receipt counter.

Existing repayment rows predate these columns; they are backfilled as
method = 'customer_portal' (the only repayment path that existed) and get no
receipt number (none was ever issued for them).

Revision ID: f1c7d3a9e2b5
Revises: e4a8c2f9b1d7
Create Date: 2026-09-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1c7d3a9e2b5'
down_revision: Union[str, Sequence[str], None] = 'e4a8c2f9b1d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_METHOD = sa.Enum('customer_portal', 'cash', 'mpesa', 'bank', name='paymentmethod')


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    company_columns = {c['name'] for c in inspector.get_columns('company')}
    if 'next_receipt_sequence' not in company_columns:
        with op.batch_alter_table('company') as batch_op:
            batch_op.add_column(
                sa.Column('next_receipt_sequence', sa.Integer(), nullable=False, server_default='1')
            )

    txn_columns = {c['name'] for c in inspector.get_columns('transaction')}
    if 'method' not in txn_columns:
        _METHOD.create(bind, checkfirst=True)
        with op.batch_alter_table('transaction') as batch_op:
            batch_op.add_column(sa.Column('method', _METHOD, nullable=True))
            batch_op.add_column(sa.Column('reference', sa.String(length=64), nullable=True))
            batch_op.add_column(sa.Column('receipt_number', sa.String(length=32), nullable=True))
            batch_op.add_column(sa.Column('recorded_by', sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column('notes', sa.String(length=500), nullable=True))
            batch_op.create_foreign_key('fk_transaction_recorded_by_user', 'user', ['recorded_by'], ['id'])
            batch_op.create_unique_constraint('uq_transaction_company_reference', ['company_id', 'reference'])
            batch_op.create_unique_constraint('uq_transaction_company_receipt', ['company_id', 'receipt_number'])

        op.execute("UPDATE \"transaction\" SET method = 'customer_portal' WHERE type = 'repayment' AND method IS NULL")


def downgrade() -> None:
    with op.batch_alter_table('transaction') as batch_op:
        batch_op.drop_constraint('uq_transaction_company_receipt', type_='unique')
        batch_op.drop_constraint('uq_transaction_company_reference', type_='unique')
        batch_op.drop_constraint('fk_transaction_recorded_by_user', type_='foreignkey')
        batch_op.drop_column('notes')
        batch_op.drop_column('recorded_by')
        batch_op.drop_column('receipt_number')
        batch_op.drop_column('reference')
        batch_op.drop_column('method')
    _METHOD.drop(op.get_bind(), checkfirst=True)
    with op.batch_alter_table('company') as batch_op:
        batch_op.drop_column('next_receipt_sequence')
