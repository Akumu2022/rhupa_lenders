from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class ReportRequest(BaseModel):
    """Query params for the parameterized date-range report (CLAUDE.md §30
    M18) — one dispatcher, not one endpoint per cadence."""

    start_date: date
    end_date: date


class ReportResponse(BaseModel):
    start_date: date
    end_date: date
    total_disbursed: Decimal
    total_collected: Decimal
    total_expenses: Decimal
    net: Decimal
    par_percentage: Decimal
    active_loans: int
