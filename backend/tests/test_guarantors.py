"""CLAUDE.md §27 (M12): guarantors and collateral, tied to a loan
application — captured by the credit officer, visible to the decision
chain, and (per-product) required before a branch manager/committee can
approve.
"""

from tests.test_credit import _auth_headers, _setup_company_with_branch_review_application


def test_credit_officer_can_add_and_view_guarantor_and_collateral(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    application_id = ctx["application"]["id"]

    add_resp = client.post(
        f"/applications/{application_id}/guarantors",
        json={
            "full_name": "Jane Guarantor",
            "id_number": "G-123456",
            "phone_number": "+254711000001",
            "guaranteed_amount": "5000.00",
            "consent": True,
        },
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert add_resp.status_code == 201, add_resp.text
    guarantor = add_resp.json()
    assert guarantor["verification_status"] == "pending"

    collateral_resp = client.post(
        f"/applications/{application_id}/collateral",
        json={"description": "Motorbike", "estimated_value": "60000.00"},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert collateral_resp.status_code == 201, collateral_resp.text

    list_resp = client.get(f"/applications/{application_id}/guarantors", headers=_auth_headers(ctx["manager_token"]))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    collateral_list_resp = client.get(
        f"/applications/{application_id}/collateral", headers=_auth_headers(ctx["manager_token"])
    )
    assert collateral_list_resp.status_code == 200
    assert len(collateral_list_resp.json()) == 1


def test_guarantor_from_another_company_is_not_found(client, engine):
    ctx_a = _setup_company_with_branch_review_application(client, engine, company_name="Company A")
    ctx_b = _setup_company_with_branch_review_application(
        client, engine, company_name="Company B", platform_token=ctx_a["platform_token"]
    )

    resp = client.get(
        f"/applications/{ctx_a['application']['id']}/guarantors", headers=_auth_headers(ctx_b["credit_token"])
    )
    assert resp.status_code == 404


def test_approval_blocked_without_verified_guarantor_when_product_requires_one(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    application_id = ctx["application"]["id"]
    product_id = ctx["loan_product"]["id"]

    patch_resp = client.patch(
        f"/admin/products/{product_id}",
        json={"requires_guarantor": True},
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert patch_resp.status_code == 200, patch_resp.text

    decide_resp = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Looks good"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert decide_resp.status_code == 400
    assert "guarantor" in decide_resp.json()["detail"].lower()

    add_resp = client.post(
        f"/applications/{application_id}/guarantors",
        json={
            "full_name": "Jane Guarantor",
            "id_number": "G-654321",
            "phone_number": "+254711000002",
            "guaranteed_amount": "5000.00",
        },
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert add_resp.status_code == 201
    guarantor_id = add_resp.json()["id"]

    still_blocked = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Looks good"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert still_blocked.status_code == 400

    verify_resp = client.patch(
        f"/applications/{application_id}/guarantors/{guarantor_id}",
        json={"verification_status": "verified"},
        headers=_auth_headers(ctx["credit_token"]),
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["verification_status"] == "verified"

    approve_resp = client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Looks good"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    assert approve_resp.status_code == 200, approve_resp.text
    assert approve_resp.json()["status"] == "approved"
