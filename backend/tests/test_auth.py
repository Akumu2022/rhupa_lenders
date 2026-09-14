from sqlmodel import Session, select

from app.models import User, UserRole
from app.security import hash_password
from app.tenancy import tenant_context
from tests.conftest import seed_super_admin


def test_login_succeeds_with_correct_credentials(client, engine):
    seed_super_admin(engine, email="a@rupha.example.com", password="correct-password")

    resp = client.post("/auth/login", json={"email": "a@rupha.example.com", "password": "correct-password"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "super_admin"
    assert body["company_id"] is None
    assert body["access_token"]


def test_login_rejects_wrong_password(client, engine):
    seed_super_admin(engine, email="a@rupha.example.com", password="correct-password")

    resp = client.post("/auth/login", json={"email": "a@rupha.example.com", "password": "wrong-password"})

    assert resp.status_code == 401


def test_login_rejects_unknown_email(client, engine):
    resp = client.post("/auth/login", json={"email": "nobody@rupha.example.com", "password": "whatever123"})
    assert resp.status_code == 401


def test_deactivated_user_cannot_login(client, engine):
    with Session(engine) as session:
        with tenant_context(None):
            user = User(
                email="gone@rupha.example.com",
                hashed_password=hash_password("some-password"),
                role=UserRole.super_admin,
                full_name="Ex Admin",
                company_id=None,
                is_active=False,
            )
            session.add(user)
            session.commit()

    resp = client.post("/auth/login", json={"email": "gone@rupha.example.com", "password": "some-password"})
    assert resp.status_code == 403


def test_deactivated_user_is_locked_out_of_protected_routes_immediately(client, engine):
    """CLAUDE.md §15: is_active is checked on every request via the central
    gate, not just at login — a still-valid JWT must not retain access."""
    seed_super_admin(engine, email="admin@rupha.example.com", password="super-secret-1")
    login = client.post("/auth/login", json={"email": "admin@rupha.example.com", "password": "super-secret-1"})
    token = login.json()["access_token"]

    with Session(engine) as session:
        with tenant_context(None):
            user = session.exec(select(User).where(User.email == "admin@rupha.example.com")).first()
            user.is_active = False
            session.add(user)
            session.commit()

    resp = client.get("/platform/companies", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Account deactivated"


def test_protected_route_requires_bearer_token(client):
    resp = client.get("/platform/companies")
    assert resp.status_code == 401
