"""Short-TTL cache for `Company.status` (CLAUDE.md §6): the suspension check
runs on every authenticated request, so it's the hot path. In-process, single-
instance cache is enough at MVP scale — no Redis. Invalidated explicitly on
every suspend/reactivate toggle so a status change is visible immediately
rather than waiting out the TTL.
"""

import time
from typing import Optional

from .models import CompanyStatus

_TTL_SECONDS = 30
_cache: dict[int, tuple[CompanyStatus, float]] = {}


def get_cached_status(company_id: int) -> Optional[CompanyStatus]:
    entry = _cache.get(company_id)
    if entry is None:
        return None
    status, expires_at = entry
    if time.monotonic() >= expires_at:
        _cache.pop(company_id, None)
        return None
    return status


def set_cached_status(company_id: int, status: CompanyStatus) -> None:
    _cache[company_id] = (status, time.monotonic() + _TTL_SECONDS)


def invalidate(company_id: int) -> None:
    _cache.pop(company_id, None)


def clear() -> None:
    """Test-only: the cache is a process-global dict keyed by company_id, and
    tests spin up fresh databases whose autoincrement ids restart at 1 — without
    clearing between tests, a stale entry from one test's "company 1" would leak
    into the next test's unrelated "company 1"."""
    _cache.clear()
