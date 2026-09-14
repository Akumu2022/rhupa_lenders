"""CLAUDE.md §12: a privileged action must never happen silently or
unattributably. One helper, called at every privileged write, so no route
hand-rolls its own audit insert and forgets a field.
"""

from typing import Optional

from sqlmodel import Session

from .models import AuditLog, User


def write_audit(
    session: Session,
    *,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: Optional[int],
    reason: Optional[str] = None,
    company_id: Optional[int] = None,
    is_platform_action: bool = False,
    is_anomaly: bool = False,
) -> AuditLog:
    entry = AuditLog(
        company_id=company_id,
        actor_id=actor.id,
        actor_email=actor.email,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        reason=reason,
        is_platform_action=is_platform_action,
        is_anomaly=is_anomaly,
    )
    session.add(entry)
    return entry


def write_system_audit(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: Optional[int],
    reason: Optional[str] = None,
    company_id: Optional[int] = None,
) -> AuditLog:
    """Same append-only trail, for an action no human triggered (e.g. daily
    penalty accrual, CLAUDE.md §23). `actor_id` is nullable on AuditLog for
    exactly this case; `actor_email` uses a fixed, unmistakable sentinel
    rather than pointing at any real user."""
    entry = AuditLog(
        company_id=company_id,
        actor_id=None,
        actor_email="system@platform",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        reason=reason,
        is_platform_action=False,
        is_anomaly=False,
    )
    session.add(entry)
    return entry
