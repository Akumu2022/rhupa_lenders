import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import company_status_cache
from app.db import get_session
from app.limiter import limiter
from app.main import app
from app.models import User, UserRole
from app.security import hash_password
from app.tenancy import tenant_context


@pytest.fixture()
def engine():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    return test_engine


@pytest.fixture()
def client(engine):
    def get_test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    limiter.reset()
    company_status_cache.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_branch(client, admin_token, *, name="Main Branch", code="MAIN", auth_headers=None) -> dict:
    """CLAUDE.md §25: credit_officer/branch_manager staff require a branch_id
    at creation (M10) — tests need a real Branch to assign them to. `code`
    must be unique per company but tests may reuse it across companies."""
    headers = auth_headers(admin_token) if auth_headers else {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/admin/branches", json={"name": name, "code": code}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def seed_super_admin(engine, email="platform-admin@rupha.example.com", password="platform-pass-123") -> User:
    """Direct DB seed — mirrors scripts/seed_super_admin.py. There is no HTTP
    route for this (CLAUDE.md §4: seeding is the one bootstrap exception)."""
    with Session(engine) as session:
        with tenant_context(None):
            user = User(
                email=email,
                hashed_password=hash_password(password),
                role=UserRole.super_admin,
                full_name="Platform Admin",
                company_id=None,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        return user
