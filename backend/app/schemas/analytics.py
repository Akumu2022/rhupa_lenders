"""Response shapes for app/routers/analytics.py — Decimal serializes as a
string (rule #13), same as every other money field in the API."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class StageCount(BaseModel):
    stage: str
    count: int
    amount: Decimal


class QueuesBlock(BaseModel):
    in_review_count: int
    in_review_amount: Decimal
    awaiting_disbursement_count: int
    awaiting_disbursement_amount: Decimal


class FlowsBlock(BaseModel):
    disbursed_count: int
    disbursed_amount: Decimal
    collected_count: int
    collected_amount: Decimal
    penalties_charged: Decimal
    due_amount: Decimal
    paid_against_due: Decimal
    collection_rate_pct: Decimal


class PortfolioBlock(BaseModel):
    active_loans: int
    overdue_loans: int
    defaulted_loans: int
    repaid_loans: int
    active_borrowers: int
    total_disbursed_all_time: Decimal
    total_repaid_all_time: Decimal
    outstanding_principal: Decimal
    outstanding_interest: Decimal
    outstanding_penalties: Decimal
    outstanding_total: Decimal
    arrears_amount: Decimal
    repayment_progress_pct: Decimal
    par_pct: Decimal


class DayDue(BaseModel):
    date: date
    count: int
    amount: Decimal


class DueBlock(BaseModel):
    today_count: int
    today_amount: Decimal
    today_collected: Decimal
    today_paid: int
    today_partial: int
    today_unpaid: int
    overdue_installments: int
    next_7_days: list[DayDue]
    next_30_days_amount: Decimal
    next_30_days_count: int


class AgingBucket(BaseModel):
    bucket: str
    count: int
    amount: Decimal


class SeriesPoint(BaseModel):
    period: date
    disbursed: Decimal
    collected: Decimal
    due: Decimal


class DueListItem(BaseModel):
    application_id: int
    loan_id: int
    customer_full_name: str
    installment_number: int
    due_date: date
    amount_remaining: Decimal
    days_past_due: int
    state: str


class DashboardResponse(BaseModel):
    start: date
    end: date
    as_of: date
    scope: str
    queues: QueuesBlock
    pipeline: list[StageCount]
    pipeline_all_time: list[StageCount]
    flows: FlowsBlock
    portfolio: PortfolioBlock
    due: DueBlock
    aging: list[AgingBucket]
    granularity: str
    series: list[SeriesPoint]
    due_list: list[DueListItem]


class ApplicationListItem(BaseModel):
    id: int
    customer_id: int
    customer_full_name: str
    customer_email: str
    loan_product_name: str
    amount_requested: Decimal
    status: str
    loan_id: Optional[int]
    loan_status: Optional[str]
    stage: str
    prepared_by_name: Optional[str]
    created_at: datetime
    reviewed_at: Optional[datetime]
    review_notes: Optional[str]
    principal: Optional[Decimal]
    outstanding_balance: Optional[Decimal]
    disbursed_at: Optional[datetime]
    next_due_date: Optional[date]
    days_past_due: int


class TimelineEvent(BaseModel):
    at: datetime
    kind: str
    title: str
    tone: str
    actor_name: Optional[str]
    detail: Optional[str]
    amount: Optional[Decimal]


class ScheduleItem(BaseModel):
    installment_number: int
    due_date: date
    amount_due: Decimal
    amount_paid: Decimal
    principal_component: Decimal
    interest_component: Decimal
    state: str
    days_past_due: int


class LoanSummary(BaseModel):
    loan_id: int
    status: str
    principal: Decimal
    interest: Decimal
    penalties: Decimal
    total_owed: Decimal
    repaid: Decimal
    outstanding_balance: Decimal
    outstanding_principal: Decimal
    outstanding_interest: Decimal
    outstanding_penalties: Decimal
    disbursed_at: Optional[datetime]
    next_due_date: Optional[date]
    days_past_due: int
    progress_pct: Decimal


class TimelineResponse(BaseModel):
    application_id: int
    customer_full_name: str
    customer_email: str
    customer_phone: Optional[str]
    customer_number: Optional[str]
    loan_product_name: str
    branch_name: Optional[str]
    amount_requested: Decimal
    stage: str
    prepared_by_name: Optional[str]
    created_at: datetime
    loan: Optional[LoanSummary]
    events: list[TimelineEvent]
    schedule: list[ScheduleItem]
