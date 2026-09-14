"""Bootstrap the platform's one and only super_admin user.

CLAUDE.md §4: seeding super_admin is "the only bootstrap exception" to the rule
that account creation always flows through a role-appropriate creator. This is
a CLI script, deliberately NOT an HTTP route — there is no /auth/register-super-
admin endpoint, and there must never be one.

Usage (from backend/):
    .venv/Scripts/python scripts/seed_super_admin.py --email you@rupha.co --full-name "Your Name" --password '...'
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from passlib.context import CryptContext
from sqlmodel import Session, select

from app.db import engine
from app.models import User, UserRole
from app.tenancy import tenant_context

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--password", help="Omit to be prompted (recommended — avoids shell history).")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Super admin password: ")
    if len(password) < 12:
        print("Refusing to seed a super_admin with a password under 12 characters.", file=sys.stderr)
        raise SystemExit(1)

    with Session(engine) as session:
        # super_admin has company_id = None — the platform bypass is the correct
        # context to check for an existing super_admin and to insert this one.
        with tenant_context(None):
            existing = session.exec(
                select(User).where(User.email == args.email)
            ).first()
            if existing is not None:
                print(f"A user with email {args.email!r} already exists.", file=sys.stderr)
                raise SystemExit(1)

            super_admin = User(
                email=args.email,
                hashed_password=pwd_context.hash(password),
                role=UserRole.super_admin,
                full_name=args.full_name,
                company_id=None,
                is_active=True,
            )
            session.add(super_admin)
            session.commit()

    print(f"Seeded super_admin: {args.email}")


if __name__ == "__main__":
    main()
