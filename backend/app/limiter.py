"""Shared slowapi limiter instance (CLAUDE.md §2): applied to /auth/login and
the customer signup endpoint, both unauthenticated and guessable/brute-forceable
otherwise. One instance so main.py's exception handler and every router agree
on the same rate-limit state.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
