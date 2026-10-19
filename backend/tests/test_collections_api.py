"""Bank (I&M) Collections API: auth, validation, payments, idempotency, tenancy."""

from decimal import Decimal

import pytest
from sqlmodel import Session, select

from app.config import settings
from app.models import Loan, Profile, Transaction
from app.tenancy import tenant_context
from tests.test_disbursement_and_repayment import _auth_headers, _setup_approved_loan

VALIDATE = "/api/v1/collections/validate"
PAYMENTS = "/api/v1/collections/payments"


@pytest.fixture
def bank(client, monkeypatch):
    monkeypatch.setattr(settings, "im_client_id", "im-client")
    monkeypatch.setattr(settings, "im_client_secret", "im-secret")
    resp = client.post(
        "/oauth/token",
        data={"grant_type": "client_credentials", "client_id": "im-client", "client_secret": "im-secret"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _customer_number(engine, ctx):
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            profile = session.exec(select(Profile)).first()
            if not profile.customer_number:
                profile.customer_number = f"CUST-{ctx['company']['id']:04d}-000001"
                session.add(profile)
                session.commit()
            return profile.customer_number


def _loan(engine, ctx):
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            return session.get(Loan, ctx["loan"]["id"])


def _payload(ref, txn="TXN-1", amount="1000.00"):
    return {
        "paymentType": "MPESA",
        "transactionReference": txn,
        "transactionDate": "2026-10-15T10:30:00",
        "amount": amount,
        "currency": "KES",
        "shortCode": "123456",
        "additions": {
            "customerRef": ref,
            "externalRefNumber": "QWE123",
            "payerName": "John Doe",
            "payerMobileNumber": "254712345678",
        },
    }


def test_disabled_until_configured(client):
    assert client.post(VALIDATE, json={"customerRef": "x"}).status_code == 404
    assert client.post("/oauth/token", data={"grant_type": "client_credentials", "client_id": "a", "client_secret": "b"}).status_code == 404


def test_bad_credentials_and_missing_token(client, bank):
    resp = client.post("/oauth/token", data={"grant_type": "client_credentials", "client_id": "im-client", "client_secret": "nope"})
    assert resp.status_code == 401
    r = client.post(VALIDATE, json={"customerRef": "x"})
    assert r.status_code == 401 and r.json()["resultCode"] == 1
    r = client.post(PAYMENTS, json={})
    assert r.status_code == 401 and r.json()["erpRefId"] is None


def test_user_access_token_is_not_a_bank_token(client, engine, bank):
    ctx = _setup_approved_loan(client, engine)
    r = client.post(VALIDATE, json={"customerRef": "x"}, headers=_auth_headers(ctx["admin_token"]))
    assert r.status_code == 401


def test_validate_found_and_not_found(client, engine, bank):
    ctx = _setup_approved_loan(client, engine)
    ref = _customer_number(engine, ctx)
    r = client.post(VALIDATE, json={"customerRef": ref}, headers=bank)
    assert r.status_code == 200
    body = r.json()
    assert body["resultCode"] == 0 and body["customerName"] and body["customerRef"] == ref
    r = client.post(VALIDATE, json={"customerRef": ref.lower().replace("-", " - ")}, headers=bank)
    assert r.status_code == 200  # case and spacing are normalized
    for bad in ("CUST-9999-000001", "garbage"):
        r = client.post(VALIDATE, json={"customerRef": bad}, headers=bank)
        assert r.status_code == 404 and r.json() == {"resultCode": 1, "message": "Customer not found", "customerName": "", "customerRef": ""}
    assert client.post(VALIDATE, json={}, headers=bank).status_code == 400


def test_payment_applies_to_loan_and_is_idempotent(client, engine, bank):
    ctx = _setup_approved_loan(client, engine)
    client.post(f"/finance/loans/{ctx['loan']['id']}/disburse", headers=_auth_headers(ctx["finance_token"]))
    ref = _customer_number(engine, ctx)
    before = _loan(engine, ctx).outstanding_balance

    r = client.post(PAYMENTS, json=_payload(ref), headers=bank)
    assert r.status_code == 200, r.text
    receipt = r.json()["erpRefId"]
    assert r.json()["resultCode"] == 0 and receipt

    assert _loan(engine, ctx).outstanding_balance == before - Decimal("1000.00")

    # Bank retry: same receipt, balance unchanged, still one ledger row.
    r2 = client.post(PAYMENTS, json=_payload(ref), headers=bank)
    assert r2.status_code == 200 and r2.json()["erpRefId"] == receipt
    assert _loan(engine, ctx).outstanding_balance == before - Decimal("1000.00")
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            rows = session.exec(select(Transaction).where(Transaction.reference == "TXN-1")).all()
    assert len(rows) == 1 and rows[0].recorded_by is None and rows[0].method.value == "mpesa"


def test_payment_rejections(client, engine, bank):
    ctx = _setup_approved_loan(client, engine)
    client.post(f"/finance/loans/{ctx['loan']['id']}/disburse", headers=_auth_headers(ctx["finance_token"]))
    ref = _customer_number(engine, ctx)

    missing = _payload(ref)
    del missing["additions"]["payerMobileNumber"]
    r = client.post(PAYMENTS, json=missing, headers=bank)
    assert r.status_code == 400 and "payerMobileNumber" in r.json()["resultDesc"] and r.json()["erpRefId"] is None

    assert client.post(PAYMENTS, json=_payload(ref, amount="99999999.00"), headers=bank).status_code == 400
    assert client.post(PAYMENTS, json=_payload(ref, amount="0"), headers=bank).status_code == 400
    assert client.post(PAYMENTS, json=_payload("CUST-9999-000001"), headers=bank).status_code == 404
    bad_currency = _payload(ref)
    bad_currency["currency"] = "USD"
    assert client.post(PAYMENTS, json=bad_currency, headers=bank).status_code == 400


def test_payment_cannot_cross_companies(client, engine, bank):
    """A reference only ever resolves inside the company it names."""
    ctx_a = _setup_approved_loan(client, engine, company_name="Company A")
    ctx_b = _setup_approved_loan(client, engine, company_name="Company B", platform_token=ctx_a["platform_token"])
    for ctx in (ctx_a, ctx_b):
        client.post(f"/finance/loans/{ctx['loan']['id']}/disburse", headers=_auth_headers(ctx["finance_token"]))
    ref_a = _customer_number(engine, ctx_a)
    before_b = _loan(engine, ctx_b).outstanding_balance

    assert client.post(PAYMENTS, json=_payload(ref_a), headers=bank).status_code == 200
    assert _loan(engine, ctx_b).outstanding_balance == before_b
