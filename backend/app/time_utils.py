"""Time helpers.

SQLite drops tzinfo on datetime round-trip (CLAUDE.md's SQLite-dev /
Postgres-prod split means app code must tolerate this on both). Every
timestamp this app writes is UTC via `datetime.now(timezone.utc)`, so a naive
value read back is UTC, not local time — never assume it's naive-local.

Calendar decisions ("what day is it", "which day did this happen on") use
the BUSINESS timezone (settings.business_timezone, Africa/Nairobi), never the
server's clock — see config.py. Use business_today() instead of
date.today() anywhere a due date, overdue status, penalty day, or reporting
day is decided.
"""

from datetime import date, datetime, time, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from .config import settings


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@lru_cache(maxsize=1)
def business_tz() -> ZoneInfo:
    return ZoneInfo(settings.business_timezone)


def business_today() -> date:
    return datetime.now(business_tz()).date()


def business_date(value: datetime) -> date:
    """The business-calendar day a stored (UTC) timestamp falls on."""
    return as_utc(value).astimezone(business_tz()).date()


def business_day_start_utc(day: date) -> datetime:
    """UTC instant at which `day` begins in the business timezone — for
    SQL range filters on UTC timestamp columns."""
    return datetime.combine(day, time.min, tzinfo=business_tz()).astimezone(timezone.utc)


def business_day_end_utc(day: date) -> datetime:
    return datetime.combine(day, time.max, tzinfo=business_tz()).astimezone(timezone.utc)
