"""CLAUDE.md §19 light exception monitoring: flags onto the audit/exceptions
list (via AuditLog.is_anomaly), never blocks — advisory, not automation
deciding. Two heuristics: many submit/reject cycles in a short window, and an
approval landed suspiciously fast after submission.
"""

from sqlmodel import Session, select

from app.models import AuditLog
from app.tenancy import tenant_context
from tests.test_credit import _auth_headers, _setup_company_with_branch_review_application


def test_fast_approval_flagged_as_anomaly(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    application_id = ctx["application"]["id"]

    resp = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Looks fine"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert resp.status_code == 200, resp.text

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            entry = session.exec(
                select(AuditLog).where(AuditLog.action == "application.approve")
            ).one()
    # The test approves within milliseconds of submission — well under the
    # 60-second "fast approval" threshold.
    assert entry.is_anomaly is True
    assert entry.reason == "Looks fine"  # never rewritten — just flagged


def test_rapid_application_submission_flagged_as_anomaly(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)  # application #1
    product_id = ctx["loan_product"]["id"]
    customer_headers = _auth_headers(ctx["customer_token"])
    manager_headers = _auth_headers(ctx["manager_token"])

    def reject(application_id):
        resp = client.post(
            f"/branch-manager/applications/{application_id}/decide",
            json={"decision": "reject", "comments": "Insufficient income"},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text

    def submit():
        resp = client.post(
            "/applications",
            json={"loan_product_id": product_id, "amount_requested": "1000.00"},
            headers=customer_headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    reject(ctx["application"]["id"])
    second = submit()  # application #2 — not yet rapid (2 within 24h)
    reject(second["id"])
    third = submit()  # application #3 within 24h — flagged

    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            entries = session.exec(
                select(AuditLog).where(AuditLog.action == "application.rapid_submission")
            ).all()

    assert len(entries) == 1
    assert entries[0].entity_id == third["id"]
    assert entries[0].is_anomaly is True
