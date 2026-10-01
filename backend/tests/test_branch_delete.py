"""Branch edit/delete by system_administrator: delete only when nothing
references the branch, always audited, never across companies."""

from sqlmodel import Session, select

from app.models import AuditLog, Branch
from app.tenancy import tenant_context
from tests.conftest import create_branch
from tests.test_branch_assignment import _company, _setup, _signup
from tests.test_credit import _auth_headers


def test_admin_deletes_an_unused_branch_with_audit(client, engine):
    _, company, admin, _, _ = _setup(client, engine)
    spare = create_branch(client, admin, name="Spare", code="SPR-01")

    resp = client.delete(f"/admin/branches/{spare['id']}", headers=_auth_headers(admin))
    assert resp.status_code == 204

    with Session(engine) as session, tenant_context(company["id"]):
        assert session.get(Branch, spare["id"]) is None
        entry = session.exec(select(AuditLog).where(AuditLog.action == "branch.delete")).one()
        assert entry.entity_id == spare["id"]
        assert "SPR-01" in entry.reason


def test_branch_in_use_cannot_be_deleted(client, engine):
    _, company, admin, _, branch = _setup(client, engine)
    assert _signup(client, company, "cust@a.example.com", branch_code=branch["code"]).status_code == 201

    resp = client.delete(f"/admin/branches/{branch['id']}", headers=_auth_headers(admin))
    assert resp.status_code == 409
    assert "1 users" in resp.json()["detail"]


def test_admin_edits_branch_details(client, engine):
    _, _, admin, _, branch = _setup(client, engine)
    resp = client.patch(
        f"/admin/branches/{branch['id']}",
        json={"name": "Nairobi CBD", "address": "Moi Ave"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 200
    assert (resp.json()["name"], resp.json()["address"]) == ("Nairobi CBD", "Moi Ave")


def test_cannot_delete_another_companys_branch(client, engine):
    platform, _, _, _, branch = _setup(client, engine)
    _, other_admin, _ = _company(client, platform, "Company B")
    resp = client.delete(f"/admin/branches/{branch['id']}", headers=_auth_headers(other_admin))
    assert resp.status_code == 404
