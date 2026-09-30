"""Database-level tenant isolation status for the platform owner.

Shows whether Postgres row-level security (app/rls.py) actually applies to
the app's database role: which role the app connects as, whether that role
bypasses RLS (a superuser or BYPASSRLS role is never subject to it), and,
per tenant table, whether RLS is enabled, forced, and who owns it. A policy
binds a non-owner role once enabled; it binds the owner only when forced.
Read-only.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session

from ..db import get_session
from ..deps import require_role
from ..models import User, UserRole
from ..rls import TENANT_TABLES

router = APIRouter(prefix="/platform", tags=["platform"])


class TableRls(BaseModel):
    table: str
    has_policy: bool
    rls_enabled: bool
    rls_forced: bool
    owned_by_app_role: bool


class DatabaseSecurityResponse(BaseModel):
    database: str
    role: str | None = None
    role_bypasses_rls: bool | None = None
    # True only when the app's role doesn't bypass RLS and, on every tenant
    # table, the policy exists, RLS is enabled, and it binds this role
    # (the role doesn't own the table, or RLS is forced).
    enforced: bool
    tables: list[TableRls] = []


@router.get("/security", response_model=DatabaseSecurityResponse)
def get_database_security(
    session: Session = Depends(get_session),
    admin: User = Depends(require_role(UserRole.super_admin)),
) -> DatabaseSecurityResponse:
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return DatabaseSecurityResponse(database=bind.dialect.name, enforced=False)

    role, bypasses = session.execute(
        text("SELECT current_user, rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
    ).one()
    rows = session.execute(
        text(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   pg_get_userbyid(c.relowner) = current_user AS owned_by_app_role,
                   EXISTS (SELECT 1 FROM pg_policies p
                           WHERE p.tablename = c.relname AND p.policyname = 'tenant_isolation') AS has_policy
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relname = ANY(:tables)
            """
        ),
        {"tables": list(TENANT_TABLES)},
    ).all()
    found = {r.relname: r for r in rows}
    tables = [
        TableRls(
            table=name,
            has_policy=bool(found[name].has_policy) if name in found else False,
            rls_enabled=bool(found[name].relrowsecurity) if name in found else False,
            rls_forced=bool(found[name].relforcerowsecurity) if name in found else False,
            owned_by_app_role=bool(found[name].owned_by_app_role) if name in found else False,
        )
        for name in TENANT_TABLES
    ]
    enforced = (not bypasses) and all(
        t.has_policy and t.rls_enabled and (t.rls_forced or not t.owned_by_app_role) for t in tables
    )
    return DatabaseSecurityResponse(
        database="postgresql", role=role, role_bypasses_rls=bool(bypasses), enforced=enforced, tables=tables
    )
