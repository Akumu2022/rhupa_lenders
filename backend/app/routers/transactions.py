"""CLAUDE.md §9/M6: customer's own transaction history. The table is
populated by M7 (simulated disbursement/repayment) — until then this
legitimately returns an empty list.
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..deps import require_role
from ..models import Transaction, User, UserRole
from ..schemas.transaction import TransactionResponse

router = APIRouter(tags=["transactions"])


@router.get("/transactions/me", response_model=list[TransactionResponse])
def get_my_transactions(
    session: Session = Depends(get_session),
    customer: User = Depends(require_role(UserRole.customer)),
) -> list[Transaction]:
    return list(
        session.exec(
            select(Transaction)
            .where(Transaction.customer_id == customer.id)
            .order_by(Transaction.created_at.desc())
        ).all()
    )
