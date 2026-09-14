"""CLAUDE.md §4: system_administrator creates their own staff; company_id is
always inherited from the creating admin, never chosen by the request body.
`branch_id` (§25) is likewise never trusted freely — it's validated against
the admin's own company before being assigned.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..audit import write_audit
from ..db import get_session
from ..deps import require_role
from ..models import AuditAction, Branch, User, UserRole
from ..schemas.user import StaffCreateRequest, UserResponse
from ..security import hash_password

router = APIRouter(prefix="/staff", tags=["staff"])

_STAFF_ROLES = (
    UserRole.credit_officer,
    UserRole.branch_manager,
    UserRole.loan_vetting_committee,
    UserRole.cashier_finance_officer,
    UserRole.management,
)
# CLAUDE.md §25: these roles operate within one branch — their queues and
# dashboards filter on it, so branch_id is mandatory for them at creation.
_BRANCH_REQUIRED_ROLES = (UserRole.credit_officer, UserRole.branch_manager)


@router.get("", response_model=list[UserResponse])
def list_staff(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> list[User]:
    return list(session.exec(select(User).where(User.role.in_(_STAFF_ROLES)).order_by(User.id)).all())


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_staff(
    body: StaffCreateRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> User:
    role = UserRole(body.role)

    branch_id = body.branch_id
    if role in _BRANCH_REQUIRED_ROLES and branch_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="branch_id is required for this role")
    if branch_id is not None:
        # session.get is tenant-scoped — a branch_id from another company
        # comes back None here, indistinguishable from "doesn't exist"
        # (CLAUDE.md §5) — never trust the request body's branch_id blindly.
        branch = session.get(Branch, branch_id)
        if branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    staff = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        role=role,
        full_name=body.full_name,
        company_id=admin.company_id,  # inherited — never from the request body
        branch_id=branch_id,
        is_active=True,
    )
    session.add(staff)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    write_audit(
        session,
        actor=admin,
        action=AuditAction.STAFF_CREATE.value,
        entity_type="User",
        entity_id=staff.id,
        reason=f"role={body.role}",
        company_id=admin.company_id,
    )
    session.commit()
    session.refresh(staff)
    return staff


def _set_staff_active(
    *,
    staff_id: int,
    active: bool,
    action: str,
    session: Session,
    admin: User,
) -> User:
    # session.get is tenant-scoped — a staff_id from another company comes
    # back None here, indistinguishable from "doesn't exist" (CLAUDE.md §5).
    staff = session.get(User, staff_id)
    if staff is None or staff.role not in _STAFF_ROLES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")

    # CLAUDE.md §14: compare-and-set, never a blind UPDATE.
    result = session.execute(
        update(User).where(User.id == staff_id, User.is_active == (not active)).values(is_active=active)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Staff member is already {'active' if active else 'inactive'}")

    write_audit(
        session,
        actor=admin,
        action=action,
        entity_type="User",
        entity_id=staff_id,
        company_id=admin.company_id,
    )
    session.commit()
    session.refresh(staff)
    return staff


@router.post("/{staff_id}/deactivate", response_model=UserResponse)
def deactivate_staff(
    staff_id: int,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> User:
    """CLAUDE.md §6: staff revocation is immediate, not "soon" — the central
    gate checks User.is_active on every request, same as company suspension."""
    return _set_staff_active(staff_id=staff_id, active=False, action=AuditAction.STAFF_DEACTIVATE.value, session=session, admin=admin)


@router.post("/{staff_id}/reactivate", response_model=UserResponse)
def reactivate_staff(
    staff_id: int,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> User:
    return _set_staff_active(staff_id=staff_id, active=True, action=AuditAction.STAFF_REACTIVATE.value, session=session, admin=admin)
