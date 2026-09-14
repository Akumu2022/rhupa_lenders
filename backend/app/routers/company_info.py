"""Read-only "who am I working for" lookup for the frontend top bar (§18: a
"current company" label for staff). Distinct from platform.py, which is the
super_admin's cross-tenant management surface — this is every other role
reading their own single company, keyed off their own JWT company_id.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..audit import write_audit
from ..db import get_session
from ..deps import get_current_user, require_role
from ..models import AuditAction, Company, User, UserRole
from ..schemas.company import CompanyProfileUpdateRequest
from ..schemas.company_info import CompanyInfoResponse

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/me", response_model=CompanyInfoResponse)
def get_my_company(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Company:
    if user.company_id is None:
        # super_admin — not scoped to any single company.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not scoped to a company")

    # Company doesn't inherit TenantMixin (it IS the tenant root), so this
    # isn't auto-filtered — but keying strictly off the authenticated user's
    # own company_id from the JWT means there's nothing for a caller to
    # supply that could reach another company's row.
    company = session.get(Company, user.company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.patch("/me", response_model=CompanyInfoResponse)
def update_my_company_profile(
    body: CompanyProfileUpdateRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.system_administrator)),
) -> Company:
    """CLAUDE.md §21: system_administrator maintains only the client-facing subset —
    contacts, address, logo, brand colors. name/legal_name/registration_number/
    signup_code are super_admin-only (set at creation, changed on /platform/...)."""
    company = session.get(Company, admin.company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(company, field, value)

    session.add(company)
    write_audit(
        session,
        actor=admin,
        action=AuditAction.COMPANY_UPDATE_PROFILE.value,
        entity_type="Company",
        entity_id=company.id,
        reason=", ".join(updates.keys()) or None,
        company_id=admin.company_id,
    )
    session.commit()
    session.refresh(company)
    return company
