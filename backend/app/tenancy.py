"""The tenant-scoping mechanism described in CLAUDE.md §5.

This is the load-bearing wall of the whole system: every tenant-owned model must
inherit TenantMixin, and every request/script must enter `tenant_context(...)`
before touching the database. If it doesn't, queries fail CLOSED (raise), not open
(silently return unscoped rows) — that's the difference between a bug and a
cross-company data leak.

Routes never write `WHERE company_id = ...` by hand. Cross-company access exists
in exactly one place: `tenant_context(None)`, used only by /platform/... routes
gated on require_role("super_admin"), and by scripts/tests that must seed or
inspect across tenants.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria
from sqlmodel import Field, SQLModel

_UNSET = object()

_current_company_id: ContextVar = ContextVar("current_company_id", default=_UNSET)


class TenantScopeNotSetError(RuntimeError):
    """A tenant-owned query executed before tenant_context() was entered.

    This means some request path skipped the auth dependency, or some script
    touched the DB without an explicit scope. Fail loudly here in dev/tests
    rather than silently leaking cross-company rows in production.
    """


class TenantMixin(SQLModel):
    """Inherit this on every tenant-owned model (User, Profile, LoanApplication, ...).

    Company itself does NOT inherit this — it's the tenant root, not a tenant-owned row.
    """

    company_id: Optional[int] = Field(default=None, foreign_key="company.id", index=True)


@contextmanager
def tenant_context(company_id: Optional[int]) -> Iterator[None]:
    """Enter the tenant scope for a request, script, or test.

    Pass the resolved company_id for a normal scoped user. Pass None only for the
    explicit super_admin/platform bypass — never as a stand-in for "not resolved yet".
    """
    token = _current_company_id.set(company_id)
    try:
        yield
    finally:
        _current_company_id.reset(token)


def _tenant_filter(execute_state) -> None:
    if not execute_state.is_select:
        return
    if execute_state.execution_options.get("skip_tenant_scope", False):
        return

    # Only enforce/raise for statements that actually touch a tenant-owned model.
    # Company itself (the tenant root) is queried before any scope can exist yet
    # — e.g. resolving a signup code — and must not be swept into this check.
    tenant_mappers = [
        mapper for mapper in execute_state.all_mappers if issubclass(mapper.class_, TenantMixin)
    ]
    if not tenant_mappers:
        return

    company_id = _current_company_id.get()

    if company_id is _UNSET:
        raise TenantScopeNotSetError(
            "A tenant-scoped query ran with no company context set. Every request "
            "must resolve the JWT and call tenant_context(...) before touching the "
            "database — see CLAUDE.md §5. This is a fail-closed guard, not a bug in "
            "your query."
        )

    if company_id is None:
        return  # explicit super_admin / platform bypass — deliberate, not default

    # Applied per concrete mapped class (not the abstract TenantMixin base) so
    # `entity_cls.company_id` is a real instrumented column, not a bare Pydantic
    # field — this still covers every current and future TenantMixin subclass
    # automatically, with no per-model registration.
    for mapper in tenant_mappers:
        entity_cls = mapper.class_
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                entity_cls,
                entity_cls.company_id == company_id,
                include_aliases=True,
            )
        )


# Registered once at import time — the mechanism is active the moment this module
# is imported anywhere in the app, not dependent on some setup step being remembered.
event.listen(Session, "do_orm_execute", _tenant_filter)
