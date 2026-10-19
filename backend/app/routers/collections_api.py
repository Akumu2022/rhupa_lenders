"""Bank-facing Collections API (I&M Business Connect "Collections API v2.0").

Unlike every other router, the CALLER here is a bank system, not a logged-in
user: I&M calls us to (1) validate a customer reference and (2) push a payment
the customer made through one of its channels. Three routes, all additive:

  POST /oauth/token                    OAuth2 client credentials -> short-lived JWT
  POST /api/v1/collections/validate    does this customerRef exist? who is it?
  POST /api/v1/collections/payments    record the payment against the customer's loan

Tenancy: there is no user and no JWT company claim. The company is derived
from the customer reference itself (CUST-{company_id:04d}-{seq}, the number
app/customer_registration.py issues) and the request then runs inside that
company's tenant_context, so the central isolation filter (CLAUDE.md §5)
applies exactly as it does for a normal request. company_id is never read from
the payload.

Disabled (404) until IM_CLIENT_ID and IM_CLIENT_SECRET are configured. The
bank-token has its own `purpose`, so it can never be used as a user access
token (decode_access_token rejects it) and vice versa.

Response bodies follow the bank spec's own shape (resultCode 0/1 in the body,
also on errors) rather than FastAPI's default {"detail": ...}.
"""

import hmac
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..limiter import limiter
from ..models import Loan, PaymentMethod, Profile, Transaction, User, UserRole
from ..repayments import REPAYABLE_LOAN_STATUSES, normalize_reference, record_repayment
from ..tenancy import tenant_context

router = APIRouter(tags=["collections-api"], include_in_schema=False)

_TOKEN_PURPOSE = "collections_client"
_TOKEN_TTL_SECONDS = 3600
_CUSTOMER_REF = re.compile(r"^CUST-(\d{4,})-\d+$")
_CENT = Decimal("0.01")

# Channel -> how it is recorded in our ledger. No new enum members: M-Pesa
# stays mpesa, every bank-side channel is bank. The exact channel and payer
# details go in the transaction notes.
_METHOD_BY_TYPE = {
    "MPESA": PaymentMethod.mpesa,
    "RTGS": PaymentMethod.bank,
    "PESALINK": PaymentMethod.bank,
    "OTG": PaymentMethod.bank,
    "BRANCH": PaymentMethod.bank,
    "CHEQUE": PaymentMethod.bank,
}
_BANK_TYPES = {"RTGS", "PESALINK", "OTG"}


def _enabled() -> bool:
    return bool(settings.im_client_id and settings.im_client_secret)


def _authenticated(request: Request) -> bool:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return False
    return payload.get("purpose") == _TOKEN_PURPOSE and payload.get("sub") == settings.im_client_id


def _validate_reply(status_code: int, message: str, name: str = "", ref: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "resultCode": 0 if status_code == 200 else 1,
            "message": message,
            "customerName": name,
            "customerRef": ref,
        },
    )


def _payment_reply(status_code: int, desc: str, erp_ref_id: Optional[str] = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"resultCode": 0 if status_code < 300 else 1, "resultDesc": desc, "erpRefId": erp_ref_id},
    )


def _company_id_from_ref(customer_ref: str) -> Optional[int]:
    match = _CUSTOMER_REF.match(normalize_reference(customer_ref) or "")
    return int(match.group(1)) if match else None


def _find_customer(session: Session, customer_ref: str) -> Optional[tuple[Profile, User]]:
    """Must be called inside tenant_context(company_id_from_ref)."""
    row = session.exec(
        select(Profile, User)
        .join(User, User.id == Profile.user_id)
        .where(Profile.customer_number == normalize_reference(customer_ref), User.role == UserRole.customer)
    ).first()
    if row is None or not row[1].is_active:
        return None
    return row


@router.post("/oauth/token", include_in_schema=False)
@limiter.limit("20/minute")
def issue_token(
    request: Request,
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
) -> JSONResponse:
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    ok = (
        grant_type == "client_credentials"
        and hmac.compare_digest(client_id.encode(), settings.im_client_id.encode())
        and hmac.compare_digest(client_secret.encode(), settings.im_client_secret.encode())
    )
    if not ok:
        return JSONResponse(status_code=401, content={"error": "invalid_client"})
    token = jwt.encode(
        {
            "sub": settings.im_client_id,
            "purpose": _TOKEN_PURPOSE,
            "exp": datetime.now(timezone.utc) + timedelta(seconds=_TOKEN_TTL_SECONDS),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return JSONResponse(content={"access_token": token, "token_type": "Bearer", "expires_in": _TOKEN_TTL_SECONDS})


@router.post("/api/v1/collections/validate", include_in_schema=False)
@limiter.limit("120/minute")
async def validate_customer(request: Request, session: Session = Depends(get_session)) -> JSONResponse:
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    if not _authenticated(request):
        return _validate_reply(401, "Authentication failed. Token missing or expired.")
    try:
        body = await request.json()
        customer_ref = str(body["customerRef"]).strip()
        if not customer_ref:
            raise KeyError
    except Exception:
        return _validate_reply(400, "Missing required field: customerRef")

    try:
        company_id = _company_id_from_ref(customer_ref)
        if company_id is None:
            return _validate_reply(404, "Customer not found")
        with tenant_context(company_id):
            found = _find_customer(session, customer_ref)
            if found is None:
                return _validate_reply(404, "Customer not found")
            profile, user = found
            return _validate_reply(200, "Customer found", user.full_name, profile.customer_number or customer_ref)
    except Exception:
        return _validate_reply(500, "An unexpected error occurred while processing the request. Please try again later.")


def _missing_field(body: dict) -> Optional[str]:
    """The spec's conditional-field rules (§4.1/4.2)."""
    for field in ("paymentType", "transactionReference", "transactionDate", "amount", "currency", "shortCode"):
        if body.get(field) in (None, ""):
            return field
    additions = body.get("additions")
    if not isinstance(additions, dict):
        return "additions"
    payment_type = str(body["paymentType"]).upper()
    required = ["customerRef", "externalRefNumber"]
    if payment_type == "MPESA":
        required += ["payerName", "payerMobileNumber"]
    if payment_type in _BANK_TYPES:
        required += ["senderBankCode", "senderAccountNumber", "senderAccountName"]
    if payment_type == "CHEQUE":
        required += ["payerName", "senderAccountNumber", "senderAccountName", "chequeNumber"]
    for field in required:
        if additions.get(field) in (None, ""):
            return f"additions.{field}"
    return None


@router.post("/api/v1/collections/payments", include_in_schema=False)
@limiter.limit("300/minute")
async def receive_payment(request: Request, session: Session = Depends(get_session)) -> JSONResponse:
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    if not _authenticated(request):
        return _payment_reply(401, "Authentication failed. Token missing, invalid, or expired.")
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError
    except Exception:
        return _payment_reply(400, "Invalid JSON payload")

    missing = _missing_field(body)
    if missing:
        return _payment_reply(400, f"Missing required field: {missing}")

    payment_type = str(body["paymentType"]).upper()
    method = _METHOD_BY_TYPE.get(payment_type)
    if method is None:
        return _payment_reply(400, f"Unsupported paymentType: {body['paymentType']}")
    if str(body["currency"]).upper() != "KES":
        return _payment_reply(400, "Unsupported currency; only KES is accepted")
    try:
        amount = Decimal(str(body["amount"]))
    except InvalidOperation:
        return _payment_reply(400, "Invalid amount")
    if amount <= 0 or amount != amount.quantize(_CENT):
        return _payment_reply(400, "Amount must be positive with at most 2 decimal places")

    additions = body["additions"]
    reference = normalize_reference(str(body["transactionReference"]))
    customer_ref = str(additions["customerRef"]).strip()
    company_id = _company_id_from_ref(customer_ref)
    if company_id is None:
        return _payment_reply(404, "Customer not found")

    notes = (
        f"{payment_type} via bank collections API; ext ref {additions['externalRefNumber']}; "
        f"shortcode {body['shortCode']}; payer {additions.get('payerName') or additions.get('senderAccountName') or '-'}"
        f"; paid at {body['transactionDate']}"
    )

    try:
        with tenant_context(company_id):
            # Idempotent: the bank retries, and the same transactionReference
            # must always answer with the same receipt, never double-apply.
            existing = session.exec(select(Transaction).where(Transaction.reference == reference)).first()
            if existing is not None:
                return _payment_reply(200, "Payment already received", existing.receipt_number)

            found = _find_customer(session, customer_ref)
            if found is None:
                return _payment_reply(404, "Customer not found")
            _, user = found

            loan = session.exec(
                select(Loan)
                .where(Loan.customer_id == user.id, Loan.status.in_(REPAYABLE_LOAN_STATUSES), Loan.outstanding_balance > 0)
                .order_by(Loan.id)
            ).first()
            if loan is None:
                return _payment_reply(400, "Customer has no loan open for repayment")
            if amount > loan.outstanding_balance:
                return _payment_reply(400, f"Amount exceeds outstanding balance of {loan.outstanding_balance}")

            transaction = record_repayment(
                session,
                loan=loan,
                amount=amount,
                actor=None,
                method=method,
                reference=reference,
                notes=notes,
            )
            return _payment_reply(200, "Payment received successfully", transaction.receipt_number)
    except HTTPException as exc:
        session.rollback()
        # A lost race on the same reference is a replay, not an error.
        if exc.status_code == 409:
            with tenant_context(company_id):
                existing = session.exec(select(Transaction).where(Transaction.reference == reference)).first()
            if existing is not None:
                return _payment_reply(200, "Payment already received", existing.receipt_number)
        return _payment_reply(exc.status_code if exc.status_code < 500 else 500, str(exc.detail))
    except Exception:
        session.rollback()
        return _payment_reply(500, "Internal server error, please try again later")
