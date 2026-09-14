"""CLAUDE.md M2: customer profile + KYC intake. Submitting sets
kyc_status = pending; the customer can resubmit only after a rejection —
never while pending or already verified (§10: no limbo, but also never
silently overwriting an in-flight or completed review).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy import update
from sqlmodel import Session, select

from ..customer_registration import next_customer_number
from ..db import get_session
from ..deps import require_role
from ..kyc_storage import save_kyc_document
from ..models import Company, KYCStatus, Profile, User, UserRole
from ..schemas.profile import ProfileResponse, ProfileSubmitForm

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileResponse)
def get_my_profile(
    session: Session = Depends(get_session),
    customer: User = Depends(require_role(UserRole.customer)),
) -> Profile:
    profile = session.exec(select(Profile).where(Profile.user_id == customer.id)).first()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No profile submitted yet")
    return profile


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def submit_profile(
    profile_data: Annotated[ProfileSubmitForm, Form()],
    session: Session = Depends(get_session),
    customer: User = Depends(require_role(UserRole.customer)),
) -> Profile:
    existing = session.exec(select(Profile).where(Profile.user_id == customer.id)).first()
    if existing is not None and existing.kyc_status != KYCStatus.rejected:
        detail = (
            "Your KYC is already verified"
            if existing.kyc_status == KYCStatus.verified
            else "A profile has already been submitted and is pending review"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    try:
        id_document_path = await save_kyc_document(
            customer.company_id, customer.id, profile_data.id_document, field_name="id_document"
        )
        id_document_back_path = await save_kyc_document(
            customer.company_id, customer.id, profile_data.id_document_back, field_name="id_document_back"
        )
        selfie_path = (
            await save_kyc_document(
                customer.company_id, customer.id, profile_data.selfie_photo, field_name="selfie_photo"
            )
            if profile_data.selfie_photo is not None
            else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # CLAUDE.md §27 (M11): the new fields are optional here but carried
    # through on both paths below — a self-signup customer may fill them in.
    extra_fields = dict(
        first_name=profile_data.first_name,
        middle_name=profile_data.middle_name,
        last_name=profile_data.last_name,
        id_type=profile_data.id_type,
        gender=profile_data.gender,
        nationality=profile_data.nationality,
        marital_status=profile_data.marital_status,
        dependants_count=profile_data.dependants_count,
        phone_number_alt=profile_data.phone_number_alt,
        next_of_kin_name=profile_data.next_of_kin_name,
        next_of_kin_relationship=profile_data.next_of_kin_relationship,
        next_of_kin_phone=profile_data.next_of_kin_phone,
    )

    if existing is not None:
        # Resubmission after rejection (CLAUDE.md §10: never limbo) — clears
        # the prior review so it goes back into the compliance queue clean.
        # customer_number is NEVER regenerated here — it identifies the
        # person, not the KYC attempt.
        #
        # CLAUDE.md §14: compare-and-set, never a blind UPDATE — the early
        # check above (existing.kyc_status != rejected) is a fast-fail for
        # the common case, but only this WHERE clause actually closes the
        # race: without it, a system_administrator override that moves this
        # same profile off `rejected` (e.g. to `verified`) between that
        # check and this write would be silently clobbered back to
        # `pending`, with no conflict and no trace of the clobber.
        result = session.execute(
            update(Profile)
            .where(Profile.id == existing.id, Profile.kyc_status == KYCStatus.rejected)
            .values(
                date_of_birth=profile_data.date_of_birth,
                national_id_number=profile_data.national_id_number,
                phone_number=profile_data.phone_number,
                residential_address=profile_data.residential_address,
                employment_status=profile_data.employment_status,
                monthly_income=profile_data.monthly_income,
                occupation=profile_data.occupation,
                id_document_path=id_document_path,
                id_document_back_path=id_document_back_path,
                selfie_path=selfie_path,
                kyc_status=KYCStatus.pending,
                reviewed_by=None,
                reviewed_at=None,
                review_notes=None,
                **extra_fields,
            )
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Profile was changed by someone else, please retry"
            )
        session.commit()
        session.refresh(existing)
        return existing

    company = session.get(Company, customer.company_id)
    customer_number = next_customer_number(session, company)

    profile = Profile(
        user_id=customer.id,
        company_id=customer.company_id,  # from the authenticated customer, never the body
        date_of_birth=profile_data.date_of_birth,
        national_id_number=profile_data.national_id_number,
        phone_number=profile_data.phone_number,
        residential_address=profile_data.residential_address,
        employment_status=profile_data.employment_status,
        monthly_income=profile_data.monthly_income,
        occupation=profile_data.occupation,
        id_document_path=id_document_path,
        id_document_back_path=id_document_back_path,
        selfie_path=selfie_path,
        kyc_status=KYCStatus.pending,
        customer_number=customer_number,
        **extra_fields,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile
