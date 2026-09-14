"""CLAUDE.md §9/§30 (M18): management — organization-wide, read-only
aggregates built on the same shared computation as /admin/portfolio/*.
"""

from sqlmodel import Session, select

from app.models import Loan
from app.tenancy import tenant_context
from tests.conftest import create_branch
from tests.test_credit import _auth_headers, _login, _setup_company_with_branch_review_application


def _add_management_staff(client, ctx, slug):
    resp = client.post(
        "/staff",
        json={
            "email": f"exec@{slug}.example.com",
            "password": "exec-pass-123",
            "full_name": "Exec One",
            "role": "management",
        },
        headers=_auth_headers(ctx["admin_token"]),
    )
    assert resp.status_code == 201, resp.text
    return _login(client, f"exec@{slug}.example.com", "exec-pass-123")


def _approve_and_disburse(client, engine, ctx):
    application_id = ctx["application"]["id"]
    client.post(
        f"/branch-manager/applications/{application_id}/decide",
        json={"decision": "approve", "comments": "Approved"},
        headers=_auth_headers(ctx["manager_token"]),
    )
    with Session(engine) as session:
        with tenant_context(ctx["company"]["id"]):
            loan_id = session.exec(select(Loan)).first().id
    disburse = client.post(f"/finance/loans/{loan_id}/disburse", headers=_auth_headers(ctx["finance_token"]))
    assert disburse.status_code == 200, disburse.text
    return loan_id


def test_management_portfolio_matches_admin_portfolio(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    exec_token = _add_management_staff(client, ctx, ctx["company"]["name"].lower().replace(" ", ""))
    _approve_and_disburse(client, engine, ctx)

    admin_summary = client.get("/admin/portfolio/summary", headers=_auth_headers(ctx["admin_token"])).json()
    mgmt_summary = client.get("/management/portfolio", headers=_auth_headers(exec_token)).json()
    assert mgmt_summary == admin_summary


def test_branch_ranking_reflects_disbursed_totals(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine, include_finance=True)
    slug = ctx["company"]["name"].lower().replace(" ", "")
    exec_token = _add_management_staff(client, ctx, slug)

    second_branch = create_branch(client, ctx["admin_token"], name="Second", code=f"{slug.upper()}-2")
    _approve_and_disburse(client, engine, ctx)

    resp = client.get("/management/branch-ranking", headers=_auth_headers(exec_token))
    assert resp.status_code == 200
    body = resp.json()
    branch_names = {b["branch_name"] for b in body}
    assert branch_names == {"Main Branch", "Second"}
    top = body[0]
    assert top["branch_name"] == "Main Branch"
    assert top["total_disbursed"] == "5000.00"
    second = next(b for b in body if b["branch_name"] == "Second")
    assert second["total_disbursed"] == "0.00"


def test_staff_performance_counts_branch_manager_decisions(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    slug = ctx["company"]["name"].lower().replace(" ", "")
    exec_token = _add_management_staff(client, ctx, slug)

    client.post(
        f"/branch-manager/applications/{ctx['application']['id']}/decide",
        json={"decision": "reject", "comments": "Insufficient income"},
        headers=_auth_headers(ctx["manager_token"]),
    )

    resp = client.get("/management/staff-performance", headers=_auth_headers(exec_token))
    assert resp.status_code == 200
    body = resp.json()
    manager_row = next(r for r in body if r["full_name"] == "Manager One")
    assert manager_row["decisions_made"] == 1
    assert manager_row["approvals"] == 0
    assert manager_row["rejections"] == 1
    # Credit officers never decide (§26 as of M13) — they carry no rows here.
    assert not any(r["full_name"] == "Credit One" for r in body)


def test_management_reports_is_tenant_isolated(client, engine):
    ctx_a = _setup_company_with_branch_review_application(client, engine, company_name="Company A", include_finance=True)
    ctx_b = _setup_company_with_branch_review_application(
        client, engine, company_name="Company B", platform_token=ctx_a["platform_token"]
    )
    exec_a_token = _add_management_staff(client, ctx_a, "companya")
    _approve_and_disburse(client, engine, ctx_a)

    from datetime import date, timedelta

    today = date.today()
    resp = client.get(
        "/management/reports",
        params={"start_date": (today - timedelta(days=1)).isoformat(), "end_date": today.isoformat()},
        headers=_auth_headers(exec_a_token),
    )
    assert resp.status_code == 200
    assert resp.json()["total_disbursed"] == "5000.00"
    assert ctx_b["application"]["id"] != ctx_a["application"]["id"]


def test_non_management_cannot_access_management_endpoints(client, engine):
    ctx = _setup_company_with_branch_review_application(client, engine)
    for endpoint in ("/management/portfolio", "/management/branch-ranking", "/management/staff-performance"):
        resp = client.get(endpoint, headers=_auth_headers(ctx["manager_token"]))
        assert resp.status_code == 403, endpoint
