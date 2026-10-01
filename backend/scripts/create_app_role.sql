-- Create the RESTRICTED database role the running app switches to.
--
-- Why: the owner role (neondb_owner) bypasses Postgres row-level security,
-- so while the app runs as the owner, the tenant_isolation policies on the
-- 16 tenant tables (app/rls.py) are never applied to it. This role owns
-- nothing and has no BYPASSRLS, so every policy applies to it.
--
-- How it is used: the app still CONNECTS as the owner (one DATABASE_URL);
-- with APP_DB_ROLE=rhupa_app set on Render it runs SET LOCAL ROLE rhupa_app
-- at the start of every transaction. The role needs no login password.
--
-- Rollback: remove APP_DB_ROLE on Render. The app then runs exactly as
-- before, with tenant isolation from the app-level filter only.
--
-- How to run: Neon console -> SQL Editor (connected as neondb_owner, on the
-- same database the app uses). Safe to re-run.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rhupa_app') THEN
    CREATE ROLE rhupa_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;

DO $$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO rhupa_app', current_database());
END
$$;
GRANT USAGE ON SCHEMA public TO rhupa_app;

-- Read and write data in every table, and use id sequences.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rhupa_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rhupa_app;

-- Tables and sequences that future migrations create (as neondb_owner) get
-- the same grants automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rhupa_app;
ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO rhupa_app;

-- Audit history: append-only for the app at the permission level too, on
-- top of the triggers that already refuse UPDATE/DELETE (CLAUDE.md §12).
REVOKE UPDATE, DELETE, TRUNCATE ON auditlog FROM rhupa_app;

-- The app never changes the schema.
REVOKE CREATE ON SCHEMA public FROM rhupa_app;

-- Let the owner switch to this role (also done by migration a9c3e5f7b1d2).
-- On Postgres 15 or older use: GRANT rhupa_app TO neondb_owner;
GRANT rhupa_app TO neondb_owner WITH SET TRUE, INHERIT FALSE;

-- Check: expect rhupa_app | f | f
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'rhupa_app';
