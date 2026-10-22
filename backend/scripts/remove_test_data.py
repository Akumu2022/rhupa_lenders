"""Remove the test company created by scripts/seed_test_data.py.

The audit log is append-only at the database level (CLAUDE.md §12) and its rows
point at the company and its users, so once anything has been done through the
app the company CAN'T be erased. This script therefore:

  1. tries a real delete of everything belonging to the test company
     (all or nothing — one transaction);
  2. if the audit trail blocks that, RETIRES it instead: company suspended,
     every user deactivated, uploaded KYC files removed. The empty shell stays
     only because history must not be rewritten.

Run from backend/:  .venv/Scripts/python scripts/remove_test_data.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, SQLModel, select

from app.config import settings
from app.db import engine
from app.models import Company, CompanyStatus, User
from app.tenancy import tenant_context

COMPANY_NAME = "ZZ TEST COMPANY (delete later)"


def hard_delete(session: Session, company_id: int) -> None:
    tables = SQLModel.metadata.sorted_tables
    # Break the user <-> branch / officer reference cycles before deleting.
    for table_name, column in (("user", "branch_id"), ("user", "assigned_officer_id"), ("branch", "manager_id")):
        table = SQLModel.metadata.tables.get(table_name)
        if table is not None and column in table.c and "company_id" in table.c:
            session.execute(update(table).where(table.c.company_id == company_id).values({column: None}))
    for table in reversed(tables):
        if table.name == "company" or "company_id" not in table.c:
            continue
        session.execute(delete(table).where(table.c.company_id == company_id))
    session.execute(delete(SQLModel.metadata.tables["company"]).where(SQLModel.metadata.tables["company"].c.id == company_id))


def main() -> None:
    with Session(engine) as session, tenant_context(None):
        company = session.exec(select(Company).where(Company.name == COMPANY_NAME)).first()
        if company is None:
            print("No test company found; nothing to remove.")
            return
        company_id = company.id

        try:
            hard_delete(session, company_id)
            session.commit()
            outcome = "deleted completely"
        except DBAPIError as exc:
            session.rollback()
            print(f"Cannot erase it ({type(exc.orig).__name__}: the audit trail is immutable). Retiring instead.")
            company = session.get(Company, company_id)
            company.status = CompanyStatus.suspended
            session.add(company)
            for user in session.exec(select(User).where(User.company_id == company_id)).all():
                user.is_active = False
                session.add(user)
            session.commit()
            outcome = "retired (suspended, all users deactivated)"

    shutil.rmtree(settings.kyc_storage_root / str(company_id), ignore_errors=True)
    print(f"Test company {company_id}: {outcome}; uploaded KYC files removed.")


if __name__ == "__main__":
    main()
