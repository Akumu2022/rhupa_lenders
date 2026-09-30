"""Add user.assigned_officer_id: the credit officer who owns a customer.

Backfill, most reliable source first:
1. the credit officer recorded as registering the customer (customer.register
   audit entry, whose actor is the registering officer);
2. otherwise the officer who most recently prepared an application for them
   (loanapplication.prepared_by).
Customers with neither (self-signups with no officer-assisted application)
stay unassigned until a branch manager or administrator assigns them.

Revision ID: b3e5a7c9d2f4
Revises: a2d4f6b8c1e3
Create Date: 2026-09-30 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3e5a7c9d2f4'
down_revision: Union[str, Sequence[str], None] = 'a2d4f6b8c1e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c['name'] for c in sa.inspect(bind).get_columns('user')}
    if 'assigned_officer_id' not in columns:
        with op.batch_alter_table('user') as batch_op:
            batch_op.add_column(sa.Column('assigned_officer_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_user_assigned_officer_user', 'user', ['assigned_officer_id'], ['id'])
            batch_op.create_index('ix_user_assigned_officer_id', ['assigned_officer_id'])

    op.execute(
        """
        UPDATE "user" SET assigned_officer_id = (
            SELECT a.actor_id FROM auditlog a
            JOIN "user" officer ON officer.id = a.actor_id
            WHERE a.action = 'customer.register'
              AND a.entity_type = 'User'
              AND a.entity_id = "user".id
              AND officer.role = 'credit_officer'
            ORDER BY a.id LIMIT 1
        )
        WHERE role = 'customer' AND assigned_officer_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE "user" SET assigned_officer_id = (
            SELECT la.prepared_by FROM loanapplication la
            WHERE la.customer_id = "user".id AND la.prepared_by IS NOT NULL
            ORDER BY la.created_at DESC LIMIT 1
        )
        WHERE role = 'customer' AND assigned_officer_id IS NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_index('ix_user_assigned_officer_id')
        batch_op.drop_constraint('fk_user_assigned_officer_user', type_='foreignkey')
        batch_op.drop_column('assigned_officer_id')
