"""Signup code generation (CLAUDE.md §7): >=10 chars of real entropy, never
sequential/guessable — it's the sole gate that assigns company_id at customer
signup, so it is generated the same way a credential would be.
"""

import secrets
import string

_ALPHABET = string.ascii_uppercase + string.digits  # 36 symbols
_LENGTH = 12  # ~62 bits of entropy — comfortably above the >=10-char floor


def generate_signup_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))
