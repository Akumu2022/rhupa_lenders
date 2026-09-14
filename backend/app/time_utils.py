"""SQLite drops tzinfo on datetime round-trip (CLAUDE.md's SQLite-dev /
Postgres-prod split means app code must tolerate this on both). Every
timestamp this app writes is UTC via `datetime.now(timezone.utc)`, so a naive
value read back is UTC, not local time — never assume it's naive-local.
"""

from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
