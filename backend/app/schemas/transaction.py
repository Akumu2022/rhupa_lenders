from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from ..models import TransactionType


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    loan_id: int
    type: TransactionType
    amount: Decimal
    created_at: datetime
