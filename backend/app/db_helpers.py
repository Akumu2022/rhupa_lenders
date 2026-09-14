"""Shared read helpers used across routers — extracted to avoid repeating
the same fail-closed "get or 404" boilerplate in every file. `session.get()`
on a TenantMixin model is already tenant-scoped (CLAUDE.md §5), so a row
belonging to another company comes back None here, indistinguishable from
"doesn't exist" — that's the intended fail-closed behavior, not something
this helper works around.
"""

from typing import Type, TypeVar

from fastapi import HTTPException, status
from sqlmodel import Session, SQLModel

ModelT = TypeVar("ModelT", bound=SQLModel)


def get_or_404(session: Session, model: Type[ModelT], id: int, detail: str = "Not found") -> ModelT:
    obj = session.get(model, id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return obj
