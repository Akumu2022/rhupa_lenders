-- EMERGENCY ROLLBACK for row-level security enforcement (migration e6b8d0f2a4c7).
-- Paste into the Neon SQL editor and run. Takes effect immediately, no deploy.
-- The app keeps working exactly as before stage 2: tenant isolation stays
-- enforced by the app-level filter (app/tenancy.py); only the database-level
-- backstop is lifted. Policies stay in place, so re-forcing is one statement
-- per table (FORCE instead of NO FORCE).
BEGIN;
ALTER TABLE "applicationreviewstage" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "auditlog" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "branch" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "businessassessment" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "expenseentry" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "guarantor" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "loan" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "loanapplication" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "loanproduct" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "mfarecoverycode" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "profile" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "referee" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "repaymentschedule" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "security" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "transaction" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "user" NO FORCE ROW LEVEL SECURITY;
COMMIT;
