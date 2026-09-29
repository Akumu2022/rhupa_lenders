"""CLAUDE.md §27 (M12): guarantors and collateral/securities, each tied to
one specific loan application. Captured by the credit officer while
preparing an application (§8: preparation includes appraisal — guarantors
and collateral are part of that same preparation work); viewed by every
role in the decision chain (credit officer, branch manager, committee,
system_administrator) so a reviewer can see them before deciding.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..audit import write_audit
from ..db import get_session
from ..deps import require_role
from ..models import AuditAction, Guarantor, LoanApplication, Security, User, UserRole
from ..schemas.guarantor import (
    GuarantorRequest,
    GuarantorResponse,
    GuarantorVerifyRequest,
    SecurityRequest,
    SecurityResponse,
)

router = APIRouter(prefix="/applications", tags=["guarantors"])

_VIEW_ROLES = (
    UserRole.credit_officer,
    UserRole.branch_manager,
    UserRole.loan_vetting_committee,
    UserRole.system_administrator,
)


def _get_application(session: Session, application_id: int, staff: User) -> LoanApplication:
    # session.get is tenant-scoped — an application_id from another company
    # comes back None here, indistinguishable from "doesn't exist" (§5).
    application = session.get(LoanApplication, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    # §5/§25: credit_officer/branch_manager are branch-scoped — an ordinary
    # hand-filtered check, same pattern as customers.py::list_customers.
    if staff.role in (UserRole.credit_officer, UserRole.branch_manager) and application.branch_id != staff.branch_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application


@router.get("/{application_id}/guarantors", response_model=list[GuarantorResponse])
def list_guarantors(
    application_id: int,
    session: Session = Depends(get_session),
    staff: User = Depends(require_role(*_VIEW_ROLES)),
) -> list[Guarantor]:
    _get_application(session, application_id, staff)
    return list(
        session.exec(
            select(Guarantor).where(Guarantor.application_id == application_id).order_by(Guarantor.id)
        ).all()
    )


@router.post("/{application_id}/guarantors", response_model=GuarantorResponse, status_code=status.HTTP_201_CREATED)
def add_guarantor(
    application_id: int,
    body: GuarantorRequest,
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.credit_officer)),
) -> Guarantor:
    application = _get_application(session, application_id, officer)
    guarantor = Guarantor(application_id=application.id, company_id=application.company_id, **body.model_dump())
    session.add(guarantor)
    session.flush()  # assigns guarantor.id for the audit entry below

    write_audit(
        session,
        actor=officer,
        action=AuditAction.GUARANTOR_ADD.value,
        entity_type="Guarantor",
        entity_id=guarantor.id,
        reason=body.full_name,
        company_id=officer.company_id,
    )
    session.commit()
    session.refresh(guarantor)
    return guarantor


@router.patch("/{application_id}/guarantors/{guarantor_id}", response_model=GuarantorResponse)
def verify_guarantor(
    application_id: int,
    guarantor_id: int,
    body: GuarantorVerifyRequest,
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.credit_officer)),
) -> Guarantor:
    _get_application(session, application_id, officer)
    guarantor = session.get(Guarantor, guarantor_id)
    if guarantor is None or guarantor.application_id != application_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guarantor not found")

    guarantor.verification_status = body.verification_status
    guarantor.verified_by = officer.id
    guarantor.verified_at = datetime.now(timezone.utc)
    session.add(guarantor)

    write_audit(
        session,
        actor=officer,
        action=AuditAction.GUARANTOR_VERIFY.value,
        entity_type="Guarantor",
        entity_id=guarantor.id,
        reason=body.verification_status.value,
        company_id=officer.company_id,
    )
    session.commit()
    session.refresh(guarantor)
    return guarantor


@router.get("/{application_id}/collateral", response_model=list[SecurityResponse])
def list_collateral(
    application_id: int,
    session: Session = Depends(get_session),
    staff: User = Depends(require_role(*_VIEW_ROLES)),
) -> list[Security]:
    _get_application(session, application_id, staff)
    return list(
        session.exec(select(Security).where(Security.application_id == application_id).order_by(Security.id)).all()
    )


@router.post("/{application_id}/collateral", response_model=SecurityResponse, status_code=status.HTTP_201_CREATED)
def add_collateral(
    application_id: int,
    body: SecurityRequest,
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.credit_officer)),
) -> Security:
    """Document upload for collateral is deferred — this captures the
    description/value now (the required fields); a document_path can be
    attached later through the same authenticated-file pattern
    (app/kyc_storage.py) once that upload flow is needed."""
    application = _get_application(session, application_id, officer)
    security = Security(application_id=application.id, company_id=application.company_id, **body.model_dump())
    session.add(security)
    session.flush()  # assigns security.id for the audit entry below

    write_audit(
        session,
        actor=officer,
        action=AuditAction.SECURITY_ADD.value,
        entity_type="Security",
        entity_id=security.id,
        reason=body.description,
        company_id=officer.company_id,
    )
    session.commit()
    session.refresh(security)
    return security
