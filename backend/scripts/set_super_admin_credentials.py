"""Change the platform owner's (super_admin) login email and password.

CLI-only, like seed_super_admin.py — there is no HTTP route for this. Runs against
whatever DATABASE_URL points at, so use it for dev.db and for production alike.

Usage (from backend/):
    .venv/Scripts/python scripts/set_super_admin_credentials.py --new-email you@x.com [--old-email current@x.com]

The password is prompted for (or read from SUPER_ADMIN_NEW_PASSWORD) so it stays out of shell history.
"""

import argparse
import getpass
import os
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
    parser.add_argument("--new-email", required=True)
    parser.add_argument("--old-email", help="Needed only when there is more than one super_admin.")
    args = parser.parse_args()

    password = os.environ.get("SUPER_ADMIN_NEW_PASSWORD") or getpass.getpass("New super admin password: ")
    if not password:
        print("Empty password refused.", file=sys.stderr)
        raise SystemExit(1)

    with Session(engine) as session:
        with tenant_context(None):
            query = select(User).where(User.role == UserRole.super_admin)
            if args.old_email:
                query = query.where(User.email == args.old_email)
            admins = session.exec(query).all()
            if len(admins) != 1:
                print(
                    f"Expected exactly one super_admin, found {len(admins)}: "
                    f"{[a.email for a in admins]}. Pass --old-email to pick one.",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            admin = admins[0]

            clash = session.exec(select(User).where(User.email == args.new_email)).first()
            if clash is not None and clash.id != admin.id:
                print(f"Email {args.new_email!r} is already used by another user.", file=sys.stderr)
                raise SystemExit(1)

            admin.email = args.new_email
            admin.hashed_password = pwd_context.hash(password)
            session.add(admin)
            session.commit()

    print(f"super_admin login is now {args.new_email}")


if __name__ == "__main__":
    main()
