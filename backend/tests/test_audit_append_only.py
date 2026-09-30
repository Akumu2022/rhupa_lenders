"""CLAUDE.md §12: the audit log is append-only at the database level: an
UPDATE or DELETE fails even when issued directly, bypassing the app."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlmodel import Session

from app.models import AuditLog
from app.tenancy import tenant_context


def _seed_entry(engine) -> int:
    with Session(engine) as session:
        with tenant_context(None):
            entry = AuditLog(company_id=None, actor_id=None, actor_email="x@y", action="test", entity_type="Test")
            session.add(entry)
            session.commit()
            return entry.id


def test_insert_still_works(engine):
    assert _seed_entry(engine) is not None


def test_update_is_rejected_by_the_database(engine):
    entry_id = _seed_entry(engine)
    # Platform scope, so row-level security (on Postgres) lets the statement
    # reach the row and it's the trigger that refuses it.
    with tenant_context(None), engine.connect() as conn:
        with pytest.raises(DatabaseError, match="append-only"):
            conn.execute(text("UPDATE auditlog SET reason = 'rewritten' WHERE id = :id"), {"id": entry_id})


def test_delete_is_rejected_by_the_database(engine):
    entry_id = _seed_entry(engine)
    with tenant_context(None), engine.connect() as conn:
        with pytest.raises(DatabaseError, match="append-only"):
            conn.execute(text("DELETE FROM auditlog WHERE id = :id"), {"id": entry_id})


def test_api_responses_carry_security_headers(client):
    resp = client.get("/health")
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
