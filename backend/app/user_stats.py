"""Staff-vs-customer user counts, shared by the super_admin platform company
detail screen (app/routers/platform.py, explicit cross-tenant, so an
optional `company_id` filter is passed by hand — the one bypass context,
CLAUDE.md §9) and the system_administrator's own users overview
(app/routers/admin.py, where the central tenant filter already scopes the
query and no hand-written company_id filter is needed or wanted, CLAUDE.md
§5). One query, one place, instead of duplicating the case()/count() SQL.
"""

from typing import Optional

from sqlalchemy import and_, case, func
from sqlmodel import Session, select

from .models import User, UserRole

_STAFF_ROLES = (
    UserRole.system_administrator,
    UserRole.credit_officer,
    UserRole.branch_manager,
    UserRole.loan_vetting_committee,
    UserRole.cashier_finance_officer,
    UserRole.management,
)


class UserCounts:
    def __init__(
        self,
        *,
        staff_total: int,
        staff_active: int,
        staff_inactive: int,
        customer_total: int,
        customer_active: int,
        customer_inactive: int,
    ) -> None:
        self.staff_total = staff_total
        self.staff_active = staff_active
        self.staff_inactive = staff_inactive
        self.customer_total = customer_total
        self.customer_active = customer_active
        self.customer_inactive = customer_inactive


def compute_user_counts(session: Session, *, company_id: Optional[int] = None) -> UserCounts:
    is_staff = User.role.in_(_STAFF_ROLES)
    is_customer = User.role == UserRole.customer

    query = select(
        func.count(case((is_staff, 1), else_=None)),
        func.count(case((and_(is_staff, User.is_active.is_(True)), 1), else_=None)),
        func.count(case((and_(is_staff, User.is_active.is_(False)), 1), else_=None)),
        func.count(case((is_customer, 1), else_=None)),
        func.count(case((and_(is_customer, User.is_active.is_(True)), 1), else_=None)),
        func.count(case((and_(is_customer, User.is_active.is_(False)), 1), else_=None)),
    )
    if company_id is not None:
        query = query.where(User.company_id == company_id)

    staff_total, staff_active, staff_inactive, customer_total, customer_active, customer_inactive = session.exec(
        query
    ).one()
    return UserCounts(
        staff_total=staff_total,
        staff_active=staff_active,
        staff_inactive=staff_inactive,
        customer_total=customer_total,
        customer_active=customer_active,
        customer_inactive=customer_inactive,
    )
