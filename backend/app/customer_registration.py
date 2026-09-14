"""CLAUDE.md §27: single source of truth for the two pieces of money-adjacent
logic M11 introduces — generating a unique customer number and computing a
business assessment's derived figures. Mirrors app/loan_calculation.py's
"one module computes it, nothing else does" discipline.
"""

from decimal import Decimal

from sqlalchemy import update
from sqlmodel import Session

from .models import Company

_ZERO = Decimal("0.00")


def next_customer_number(session: Session, company: Company) -> str:
    """Assigns the next sequential customer number for `company`, via
    compare-and-set (CLAUDE.md rule #14) so two concurrent registrations
    never get the same number. Call exactly once, at first Profile creation
    — never regenerate on a later resubmission.
    """
    while True:
        current = company.next_customer_sequence
        result = session.execute(
            update(Company)
            .where(Company.id == company.id, Company.next_customer_sequence == current)
            .values(next_customer_sequence=current + 1)
        )
        if result.rowcount == 1:
            company.next_customer_sequence = current + 1
            return f"CUST-{company.id:04d}-{current:06d}"
        session.refresh(company)  # someone else incremented it first — retry with fresh state


def compute_business_figures(
    *, total_income: Decimal, total_expenses: Decimal, existing_debt_obligations: Decimal
) -> tuple[Decimal, Decimal]:
    """CLAUDE.md §27: net_income = total_income - total_expenses;
    debt_service_capacity = net_income - existing_debt_obligations (the
    PRD's "available income" read as net_income — what's actually left to
    service debt with). Never accept either as client input."""
    net_income = total_income - total_expenses
    debt_service_capacity = net_income - existing_debt_obligations
    return net_income, debt_service_capacity
