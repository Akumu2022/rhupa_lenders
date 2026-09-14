"""CLAUDE.md M3: KYC queue — Handoff 1 seam (§10). As of M10 (§3), gated on
`credit_officer` rather than the retired `compliance_officer` role — the
client PRD folds KYC capture/verification into the Credit Officer's own
duties, with no separate KYC-approver role. Verify/reject are guarded
compare-and-set updates (§14) that write an audit entry (§12); the KYC
document endpoint is authenticated, tenant-scoped, and role-gated rather than
a static path (§9, §16).
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import update
from sqlmodel import Session, select

from ..audit import write_audit
from ..config import settings
from ..db import get_session
from ..deps import require_role
from ..models import AuditAction, KYCStatus, Profile, User, UserRole
from ..schemas.compliance import ComplianceProfileResponse, KYCRejectRequest, KYCVerifyRequest

router = APIRouter(prefix="/compliance", tags=["compliance"])


def _to_response(profile: Profile, customer: User) -> ComplianceProfileResponse:
    return ComplianceProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        kyc_status=profile.kyc_status,
        date_of_birth=profile.date_of_birth,
        national_id_number=profile.national_id_number,
        phone_number=profile.phone_number,
        residential_address=profile.residential_address,
        employment_status=profile.employment_status,
        monthly_income=profile.monthly_income,
        occupation=profile.occupation,
        has_id_document_back=profile.id_document_back_path is not None,
        has_selfie=profile.selfie_path is not None,
        created_at=profile.created_at,
        reviewed_by=profile.reviewed_by,
        reviewed_at=profile.reviewed_at,
        review_notes=profile.review_notes,
        customer_full_name=customer.full_name,
        customer_email=customer.email,
        # CLAUDE.md §27 (M11)
        customer_number=profile.customer_number,
        first_name=profile.first_name,
        middle_name=profile.middle_name,
        last_name=profile.last_name,
        id_type=profile.id_type,
        gender=profile.gender,
        nationality=profile.nationality,
        marital_status=profile.marital_status,
        dependants_count=profile.dependants_count,
        phone_number_alt=profile.phone_number_alt,
        next_of_kin_name=profile.next_of_kin_name,
        next_of_kin_relationship=profile.next_of_kin_relationship,
        next_of_kin_phone=profile.next_of_kin_phone,
    )


def _get_profile_and_customer(session: Session, profile_id: int) -> tuple[Profile, User]:
    # session.get() is still routed through the tenant-scope listener for a
    # fresh (not-yet-loaded) row, so a profile belonging to another company
    # comes back as None here — indistinguishable from "doesn't exist",
    # which is the correct fail-closed behavior.
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    customer = session.get(User, profile.user_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile, customer


@router.get("/queue", response_model=list[ComplianceProfileResponse])
def get_kyc_queue(
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.credit_officer)),
) -> list[ComplianceProfileResponse]:
    rows = session.exec(
        select(Profile, User)
        .join(User, User.id == Profile.user_id)
        .where(Profile.kyc_status == KYCStatus.pending)
        .order_by(Profile.created_at)
    ).all()
    return [_to_response(profile, customer) for profile, customer in rows]


@router.get("/history", response_model=list[ComplianceProfileResponse])
def get_kyc_history(
    session: Session = Depends(get_session),
    # CLAUDE.md §9: accountability — every decision stays visible for future
    # reference, not just while it's pending. system_administrator gets the same
    # view via /admin/kyc; this is the compliance officer's own copy of it.
    staff: User = Depends(require_role(UserRole.credit_officer, UserRole.system_administrator)),
) -> list[ComplianceProfileResponse]:
    rows = session.exec(
        select(Profile, User).join(User, User.id == Profile.user_id).order_by(Profile.created_at.desc())
    ).all()
    return [_to_response(profile, customer) for profile, customer in rows]


@router.get("/profiles/{profile_id}", response_model=ComplianceProfileResponse)
def get_profile_detail(
    profile_id: int,
    session: Session = Depends(get_session),
    # CLAUDE.md §9: system_administrator may view a profile for oversight, but only
    # credit_officer may act on it (verify/reject below).
    staff: User = Depends(require_role(UserRole.credit_officer, UserRole.system_administrator)),
) -> ComplianceProfileResponse:
    profile, customer = _get_profile_and_customer(session, profile_id)
    return _to_response(profile, customer)


@router.post("/profiles/{profile_id}/verify", response_model=ComplianceProfileResponse)
def verify_profile(
    profile_id: int,
    body: KYCVerifyRequest,
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.credit_officer)),
) -> ComplianceProfileResponse:
    _get_profile_and_customer(session, profile_id)  # 404s if not in this company

    # CLAUDE.md §14: compare-and-set, never a blind UPDATE.
    result = session.execute(
        update(Profile)
        .where(Profile.id == profile_id, Profile.kyc_status == KYCStatus.pending)
        .values(
            kyc_status=KYCStatus.verified,
            reviewed_by=officer.id,
            reviewed_at=datetime.now(timezone.utc),
            review_notes=body.notes,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile is not pending review")

    write_audit(
        session,
        actor=officer,
        action=AuditAction.KYC_VERIFY.value,
        entity_type="Profile",
        entity_id=profile_id,
        reason=body.notes,
        company_id=officer.company_id,
    )
    session.commit()

    profile, customer = _get_profile_and_customer(session, profile_id)
    return _to_response(profile, customer)


@router.post("/profiles/{profile_id}/reject", response_model=ComplianceProfileResponse)
def reject_profile(
    profile_id: int,
    body: KYCRejectRequest,
    session: Session = Depends(get_session),
    officer: User = Depends(require_role(UserRole.credit_officer)),
) -> ComplianceProfileResponse:
    _get_profile_and_customer(session, profile_id)  # 404s if not in this company

    result = session.execute(
        update(Profile)
        .where(Profile.id == profile_id, Profile.kyc_status == KYCStatus.pending)
        .values(
            kyc_status=KYCStatus.rejected,
            reviewed_by=officer.id,
            reviewed_at=datetime.now(timezone.utc),
            review_notes=body.reason,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile is not pending review")

    write_audit(
        session,
        actor=officer,
        action=AuditAction.KYC_REJECT.value,
        entity_type="Profile",
        entity_id=profile_id,
        reason=body.reason,
        company_id=officer.company_id,
    )
    session.commit()

    profile, customer = _get_profile_and_customer(session, profile_id)
    return _to_response(profile, customer)


@router.get("/profiles/{profile_id}/document/{kind}")
def get_profile_document(
    profile_id: int,
    kind: Literal["id_document", "id_document_back", "selfie"],
    session: Session = Depends(get_session),
    staff: User = Depends(require_role(UserRole.credit_officer, UserRole.system_administrator)),
) -> FileResponse:
    profile, _ = _get_profile_and_customer(session, profile_id)

    relative_path = {
        "id_document": profile.id_document_path,
        "id_document_back": profile.id_document_back_path,
        "selfie": profile.selfie_path,
    }[kind]
    if relative_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such document")

    full_path = (settings.kyc_storage_root / relative_path).resolve()
    # Defense in depth: relative_path is always generated server-side (never
    # user input), but confirm it still resolves under the storage root
    # before opening it — never trust a stored path blindly.
    if settings.kyc_storage_root not in full_path.parents and full_path != settings.kyc_storage_root:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such document")
    if not full_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such document")

    return FileResponse(full_path)
