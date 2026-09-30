"""Machine-to-machine endpoints for scheduled jobs. Not for people: no JWT,
authenticated by a shared secret (CRON_SECRET) in the X-Cron-Secret header.
Disabled entirely (404) when CRON_SECRET is not configured.
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlmodel import Session

from ..config import settings
from ..db import get_session
from ..end_of_day import run_end_of_day

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def _require_cron_secret(x_cron_secret: str | None = Header(default=None)) -> None:
    expected = settings.cron_secret
    if not expected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid cron secret")


@router.post("/end-of-day", dependencies=[Depends(_require_cron_secret)])
def end_of_day(session: Session = Depends(get_session)) -> dict:
    result = run_end_of_day(session)
    if result.failed_company_ids:
        # Surface a partial failure to the scheduler (the job goes red) while
        # the companies that succeeded keep their committed results.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"business_date": result.business_date, "failed_company_ids": result.failed_company_ids},
        )
    return {
        "business_date": result.business_date,
        "companies": len(result.companies),
        "newly_overdue": sum(c.newly_overdue for c in result.companies),
        "back_to_active": sum(c.back_to_active for c in result.companies),
        "penalty_total": str(sum((c.penalty_total for c in result.companies), 0)),
    }
