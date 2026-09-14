"""CLAUDE.md M4: every company is seeded with a small fixed catalog of loan
products at creation time — there is no product-authoring UI yet (deferred to
M8's configuration surface).
"""

from decimal import Decimal

from sqlmodel import Session

from .models import LoanProduct

_DEFAULT_PRODUCTS = [
    {
        "name": "Salary Advance",
        "description": "Short-term advance against your next salary.",
        "min_amount": Decimal("1000.00"),
        "max_amount": Decimal("50000.00"),
        "interest_rate": Decimal("5.00"),
        "repayment_period_days": 30,
    },
    {
        "name": "Emergency Loan",
        "description": "Fast cash for unexpected expenses.",
        "min_amount": Decimal("500.00"),
        "max_amount": Decimal("20000.00"),
        "interest_rate": Decimal("8.00"),
        "repayment_period_days": 14,
    },
    {
        "name": "Business Loan",
        "description": "Working capital for small businesses.",
        "min_amount": Decimal("5000.00"),
        "max_amount": Decimal("200000.00"),
        "interest_rate": Decimal("12.00"),
        "repayment_period_days": 90,
    },
]


def seed_default_loan_products(session: Session, company_id: int) -> None:
    for defaults in _DEFAULT_PRODUCTS:
        session.add(LoanProduct(company_id=company_id, **defaults))
