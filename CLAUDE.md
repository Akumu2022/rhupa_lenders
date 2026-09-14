# CLAUDE.md — Rupha Royals Digital Lending Platform (Multi-Tenant MVP)

> Project-context file. Read this first, every session. It defines the architecture,
> the rules that must not be broken, the tech stack, and the build order. When in doubt,
> follow the "Non-Negotiable Rules" — they override convenience. This is a financial,
> multi-tenant application: correctness, tenant isolation, and traceability beat brevity.

---

## 1. What we are building

A **multi-tenant digital lending platform** (SaaS) for the Kenyan market. Many independent
lending **companies (tenants)** run on one platform, each fully walled off from the others.
The platform owner (you) sits above all of them as **super admin**.

This is a deliberately trimmed version of a much larger PRD. The MVP builds the **core lending
loop only**, plus a **thin tenancy layer**. Everything not essential is cut or deferred.

**Core loop (per company):** a customer registers → gets identity-verified (KYC) → applies for
a loan → a credit officer approves → the loan is disbursed (simulated) → the customer repays.

**Guiding constraints:**
- **Zero external paid services at the start.** No real M-Pesa/bank APIs, no SMS/WhatsApp
  gateways, no biometric SDKs, no CRB/credit-bureau integrations, no AI/ML scoring services.
- **Manual verification and approval at the start.** Humans (compliance, credit officers)
  decide. Automation is advisory only and comes later.
- **One backend, one web frontend.** A Flutter app may come later; if so it consumes the *same*
  API. Do not build two clients before one is proven.
- **Thin tenancy, not a full SaaS platform.** Build isolation, company lifecycle (suspend), and
  signup-by-code. DEFER billing, plans, usage caps, subdomains-as-product, per-tenant theming.

---

## 2. Tech Stack

**Backend — FastAPI (Python)**
- ORM: **SQLModel** (SQLAlchemy + Pydantic in one).
- Migrations: **Alembic**.
- Auth: **JWT** via `python-jose`; password hashing via `passlib[bcrypt]`. Access tokens are
  **short-lived (30–60 min)**; there is no refresh-token flow in the MVP — the frontend simply
  re-prompts login on expiry. This keeps a deactivated user's residual access window small without
  building refresh-token revocation.
- Validation: **Pydantic** (built in).
- Rate limiting: **slowapi** on `/auth/login` and the customer signup endpoint (see §7) — both are
  unauthenticated and guessable/brute-forceable otherwise.
- Scheduled jobs (later, e.g. repayment reminders): **APScheduler** in-process or a cron script.
  No Celery/Redis at this scale.
- **Money is never `float`.** Every monetary column (`amount`, `balance`, `principal`, `fees`, …)
  is `Decimal` in Python, `Numeric(12, 2)` at the DB layer. Getting this wrong is invisible in dev
  and catastrophic in a ledger — decide it once, in M0, not when the first rounding bug appears.

**Frontend — React**
- Build: **Vite**. Routing: **React Router**.
- Server state: **TanStack Query (React Query)**.
- Forms: **React Hook Form + Zod** (Zod schemas mirror the Pydantic models).
- UI: **Tailwind + shadcn/ui** (or Mantine for more prebuilt tables/date-pickers).
- Auth: store the JWT; attach it via a fetch/Axios interceptor.

**Database**
- **SQLite** for dev (zero setup). **PostgreSQL** on deploy. SQLModel makes the swap trivial.
- Tenancy model: **shared database + `company_id` tenant column** (see §5). Do NOT use
  schema-per-tenant or DB-per-tenant now — unjustified cost/complexity at this stage.

**Repo shape**
```
/backend    → FastAPI app (models, routers, auth, tenancy, schemas, migrations)
/frontend   → React + Vite
CLAUDE.md   → this file
.claudeignore → excludes .env, uploaded-ID storage, lockfiles, build artifacts
```

**Admin panel note:** FastAPI + React means **no free auto-admin** (unlike Django). Staff/admin
screens are hand-built React. If internal CRUD becomes a bottleneck, **SQLAdmin** (auto-admin
over SQLModel) may be bolted on for internal use while React focuses on customer-facing screens.

---

## 3. Tenancy — Roles & Hierarchy

Multi-tenant, so there is a platform tier ABOVE the company tier. Below the company tier is a
second, **non-isolating** organizational dimension — the **branch** — matching the client PRD's
own branch-network structure (§25 has the full rationale and entity shape).

```
super_admin              (you — the platform; company_id = null; sees/manages ALL companies)
      │  creates a Company + seeds its first system_administrator
      ▼
system_administrator     (a client company's own administrator; scoped to ONE company)
      │  creates Branches, then staff assigned to a Branch
      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Branch (company-scoped org unit — NOT a tenant boundary, see §5)         │
│                                                                           │
│   credit_officer · branch_manager        (branch-scoped: branch_id set) │
│   loan_vetting_committee · cashier_finance_officer · management          │
│                              (company-wide by default: branch_id null)  │
└─────────────────────────────────────────────────────────────────────────┘
      │
      ▼
customer                                 (that company's borrowers; one company + one branch)
```

Role enum:
```
super_admin, system_administrator, credit_officer, branch_manager,
loan_vetting_committee, cashier_finance_officer, management, customer
```

- **`super_admin`** belongs to the platform, not a tenant (`company_id = null`). Only role that
  may act across companies, and only via explicit platform endpoints (`/platform/...`).
- **`system_administrator`** is the per-company superset + correction mechanism (renamed from
  the earlier "company_admin" once the client PRD's own role name was adopted). Manages users,
  branches, roles, system settings, products, and security for their one company (client PRD §1).
- **`credit_officer`** — customer recruitment, KYC/identity capture, business appraisal,
  disbursement preparation, and collections (client PRD §2–3, §7). Absorbs what an earlier MVP
  draft split out as a separate `compliance_officer` role — the PRD gives KYC capture to Credit
  Officer with no separate KYC-approver role, so that split is retired.
- **`branch_manager`** — branch performance, first-line loan approval within a delegated limit,
  supervision, portfolio management for their one branch (client PRD §10–12).
- **`loan_vetting_committee`** — reviews/approves loans that exceed a branch manager's delegated
  limit (client PRD §5); typically company-wide, not tied to one branch.
- **`cashier_finance_officer`** — receipts, payments, reconciliation, financial reports
  (client PRD §14); typically company-wide.
- **`management`** — organization-wide monitoring and reporting for their one company
  (client PRD §1, §15); read-only aggregates, company-wide.
- Everyone below `super_admin` is scoped to exactly **one** company and can NEVER see another
  company's data. `credit_officer` and `branch_manager` are additionally scoped to exactly one
  **branch** for their day-to-day queues (their dashboards filter on `branch_id`), but this is an
  ordinary query filter, not a security boundary — see §5.

---

## 4. Auth Model

**One `users` table, one login, one public registration.** Never build separate auth stacks
per role or per company.

- Authentication = "who you are" → `/auth/login`, issues a **JWT carrying BOTH the role claim
  AND the `company_id` claim** (null for super_admin).
- Authorization = "what you may do" → a `require_role(*allowed)` FastAPI dependency guards each
  endpoint. Tenancy is enforced separately and globally (see §5).

**Account creation paths (critical — three tiers):**
- **super_admin** is **seeded** directly into the DB via a one-off script (only bootstrap exception).
- **super_admin creates companies** and **seeds each company's first `system_administrator`**.
- **system_administrator creates Branches**, then **creates their own staff**
  (`credit_officer`, `branch_manager`, `loan_vetting_committee`, `cashier_finance_officer`,
  `management`). Staff `company_id` is **inherited from the creating admin**, never chosen.
  `branch_id` is **required** for `credit_officer`/`branch_manager` (must reference a branch
  belonging to the admin's own company — validated server-side, never trusted from elsewhere)
  and **optional** for the company-wide roles (`loan_vetting_committee`,
  `cashier_finance_officer`, `management`).
- **customers self-register via a company signup code** (see §7). `role = customer` hardcoded;
  `company_id` resolved from the code server-side. (Branch assignment for customers is a later
  milestone — see §14 M11 — the MVP signup code only resolves `company_id`.)

**Registration never accepts `role` OR `company_id` from the request body.** The body may carry
the customer's own details and the *signup code* — nothing that lets them cross a role or tenant
boundary.

**Frontend:** one role-aware, tenant-aware React app. Route by role after login; every view is
implicitly scoped to the user's company. The frontend guard is **UX only** — the backend always
enforces.

---

## 5. Tenant Isolation (the load-bearing wall)

**Every tenant-owned row carries `company_id`.** Add it to: `User`, `Branch`, `Profile`,
`LoanProduct`, `LoanApplication`, `Loan`, `RepaymentSchedule`, `Transaction`, `AuditLog`. The
`Company` table is the tenant root. `super_admin` users have `company_id = null`.

**`Branch` is a company-scoped org unit, NOT a second isolation boundary (§3, §25).** It carries
`company_id` like every other tenant-owned row and is subject to the exact same central filter —
but `branch_id` on `User`/`LoanApplication`/etc. is an **ordinary, hand-filterable column**, the
same way `status` is. Routes and dashboards MAY filter `WHERE branch_id = ...` by hand (e.g. a
branch manager's queue, a credit officer's portfolio) — that is not the load-bearing wall and
doing it explicitly is correct, unlike `company_id` which must never be hand-filtered. The reason
for the asymmetry: `management` and `cashier_finance_officer` routinely need company-wide,
cross-branch rollups (branch ranking, org-wide PAR/P&L) — normal behavior *within* one tenant,
whereas cross-*company* access is never normal and exists only via `/platform/...`.

**THE most important rule in the system:**

> **Every tenant query is automatically scoped to the current user's `company_id`, enforced in
> ONE central place — never hand-written per endpoint.**

**The mechanism (decided, not optional — build exactly this in M0):**
1. An `auth` dependency resolves the JWT once per request and sets a `ContextVar[int | None]`
   holding the current `company_id` (`None` only for `super_admin`).
2. A SQLAlchemy `do_orm_execute` event listener, registered globally on the session, reads that
   `ContextVar` and injects a `WHERE company_id = :cid` filter (via `with_loader_criteria`) into
   **every** SELECT against a tenant-owned model — automatically, with no per-route code.
3. Routes never write `WHERE company_id = ...` by hand. If a route needs cross-company access, it
   must be under `/platform/...`, gated `require_role("super_admin")`, and must explicitly bypass
   the listener (e.g. a flag on the session), never work around it by hand-filtering.
4. **This mechanism ships with an automated test suite in M0, before any business logic is
   written**: for each tenant-owned model, a test creates rows in two companies and asserts a
   user scoped to Company A gets **zero** rows querying Company B, through the ORM layer directly
   (not just through one endpoint). Every later milestone that adds a tenant-owned model extends
   this suite — it is a merge gate, not a nice-to-have, because this is the one rule whose failure
   is silent and catastrophic (one company seeing another's borrowers' national IDs).
- **`super_admin` is the only cross-company role**, and only via explicit `/platform/...`
  endpoints — never by accident.
- **PostgreSQL Row-Level Security is a stated, accepted MVP risk, not deferred busywork.** The
  app-layer mechanism above is the only enforcement until RLS lands — write that down as a known
  gap in the deploy checklist, and prioritize RLS as the first hardening item post-MVP, not an
  optional someday. RLS is the only backstop that catches a bug *in* the central mechanism itself.

---

## 6. Company Lifecycle & Suspension (per-tenant kill switch)

Requirement: stop Company A's service (e.g. non-payment) **without affecting Company B**.
This is manual lifecycle control by super_admin — NOT billing/invoicing/auto-suspension.

**`Company.status` ladder:**
```
active → suspended → active     (toggle; may add trial/closed later)
```

**Enforcement — one central gate, on the path that already resolves `company_id`:**
> After resolving the user's company, check its status. If `suspended`, reject the request
> (`403`, code `company_suspended`) for that company — **except** whitelisted actions (below).
Because the check keys on `company_id`, suspending A **cannot** affect B. `super_admin` is exempt
(must still see/re-activate suspended companies).

**The same gate also checks `User.is_active`, not just company status.** Company suspension stops
*a whole tenant*; individual staff revocation (a system_administrator deactivating a credit_officer
who left) is a separate, more common case, and it must not wait for a short-lived JWT to expire on its
own — check `is_active` on every request, in the same place, so a deactivated user is locked out
immediately rather than merely "soon."

**Suspension policy (humane, not a sledgehammer) — the allow-list:**
- **Company staff/admin:** blocked from operating (this is the lever on the party who owes you).
- **New applications / disbursements:** stopped.
- **Existing repayments:** **allowed to continue** (do not trap borrowers with debts they owe;
  keeps the loan books clean). *← default policy; confirm per business preference.*
- **Customer read-only access:** optional.
- **New signups into a suspended company:** blocked (see §7).

**Super admin surface:** toggle `active ⇄ suspended`; each toggle **writes a platform-level audit
entry** (who, which company, when, why — reason required). Suspending a client's whole service is
serious and must never be silent. **Cache company status** (short TTL / invalidate on toggle) —
it's on the hot path.

---

## 7. Customer Onboarding — Signup by Company Code

A customer who signs up for Company A must be assigned to A automatically and safely.

**Mechanism:** the client presents a **code**, never a raw `company_id`. The **server** resolves
code → company and stamps `company_id`. The user never picks/sees/sends a `company_id`.

- Each `Company` has a unique, indexed **`signup_code`** — generated with `secrets.token_urlsafe`
  or Crockford base32, **minimum 10 characters** of real entropy (NOT sequential like
  `company-1`; it identifies a company, it is not a password, but it must not be brute-forceable
  either — it's the only gate assigning `company_id`).
- Generated when super_admin creates the company. Company_admin can view it (to share) and
  optionally **regenerate** it (existing users are keyed by `company_id`, so unaffected).
- The signup endpoint is **rate-limited** (see §2) — an attacker should not be able to enumerate
  valid codes by brute force even at 10 chars of entropy; rate limiting is the second layer, not
  a substitute for entropy.

**Two entry points, same backend:**
- **Company code** typed on the registration form (e.g. `RUPHA-A7X`), and/or
- **Per-company signup link / subdomain** (e.g. `/apply/RUPHA-A7X`) — code baked into the URL,
  smoother for a company marketing to its own borrowers. *(Preferred.)*

**Signup flow:**
```
Customer opens Company A link (code in URL) OR types code
   ▼ server resolves signup_code → Company A (company_id = A)
   ▼ validate: code exists?  AND  Company A is active (not suspended)?
   ▼ create user: role = customer (hardcoded), company_id = A (from code, NOT body),
                  kyc_status = pending
```

**Validation guards (all server-side):**
1. Code must resolve to a real company; unknown/expired → reject ("Invalid company code").
   Never create a company-less (orphan) user — a null `company_id` is a dangerous cross-tenant hole.
2. Resolved company must be **active**, not suspended (don't let a non-paying company keep growing).
3. `role` and `company_id` come from the server, never the body.

**Staff do NOT use the signup code** — they are created by their system_administrator and inherit
`company_id`. The code is the customer on-ramp only.

---

## 8. Separation of Duties (within each company)

Orthogonal to tenancy; operates inside each tenant. The point: **no single person takes a loan
from identity to disbursement.** This is a fraud control, and it now runs across the client
PRD's full multi-stage chain (implemented in M13 — see §14 roadmap and §26 for the detailed spec):

```
Customer → Credit Officer → Branch Manager → [Loan Vetting Committee, if above the branch's
           delegated limit] → Cashier/Finance Officer → Disbursement
```

- **Credit officer** registers the customer, captures KYC/identity and the business assessment,
  and prepares the application. Does NOT decide it.
- **Branch manager** decides applications within their branch's delegated limit (approve/reject),
  or escalates above it to the committee. Does NOT act on applications they themselves registered
  (they don't register customers, but the rule generalizes: see the no-self-approval rule below).
- **Loan vetting committee** decides applications above the delegated limit. Only ever acts on
  applications already reviewed by a branch manager.
- **Cashier/finance officer** signs off before disbursement (reconciliation), and executes the
  simulated disbursement itself.
- **`system_administrator`** is the per-company superset **and correction mechanism** — see
  override rule.

**No-self-approval rule (client PRD §5):** the same user may never occupy two stages of one
application's decision chain — e.g. a branch manager may not also sit on the vetting committee
decision for an application they already decided, and no single officer may register, approve,
AND disburse the same application. Enforced at write time: each stage transition checks that the
acting user's id does not already appear as the actor on an earlier stage of the same
application (see §26 for the exact mechanism once M13 ships).

### system_administrator override rule
May override/reverse decisions below (reactivate a wrongly-rejected application, revoke a KYC
verification if fraud surfaces), BUT:
- An **exceptional, explicit** action ("Override decision"), separate from normal approve/reject.
- **Never a mandatory final step** in the normal flow. The normal path ends at the officer's decision.
- **Requires a written reason** and writes a **distinct audit entry** (original decision, who
  overrode, why). Must be **rare and visible** (exceptions list).
- **Anomaly guard:** overriding is the one place a system_administrator can single-handedly touch
  both halves of the KYC/credit separation-of-duties control that §8 exists to enforce. If the
  **same system_administrator** overrides **both** a KYC decision **and** a loan decision **on the
  same applicant**, that is exactly the one-person-does-everything scenario separation of duties
  is meant to prevent — flag it in the exceptions list distinctly (not just log it identically to a
  single override), so it's visible to whoever reviews that list, not just recoverable by
  cross-referencing the audit log by hand. Once the multi-stage chain (M13) ships, extend this
  guard to any two stages of the same application, not just KYC+loan.

**Planned later (before real money moves):** today `system_administrator` already holds both the
technical admin surface (users/branches/roles/config) AND the business-override power described
above — the client PRD's own role list doesn't split these further, so this project won't invent
a role the client didn't ask for. If a future engagement needs it, split `system_administrator`
into a technical **System Administrator** (users/roles/config; no business override) and a
**senior business role** (business override; no config) — the override plumbing built now
carries over unchanged.

---

## 9. Data Scope & Dashboards

**Principle:** each dashboard shows only what that role needs — nothing from another role's job,
another customer, or another company. **Backend enforces every boundary; the dashboard reflects
it.** Every query scoped by user + role + `company_id` server-side.

**Customer:** own loan limit/available credit, own active loans + status + balance, own repayment
schedule, "repay now", own transaction history, own application status (incl. rejection reason),
own KYC status/banner, own editable profile, a simple standing indicator.
- **Never:** other customers' data; **raw credit score or scoring logic**; staff notes; reviewer
  identities; portfolio figures; anything from another company.

**Credit officer:** own branch's KYC/registration queue, business-assessment intake, own
pending-applications queue (own branch); per application — profile, KYC documents, income/
expenses, documents, past-loan repayment history, guarantors/securities, and (later) an
**advisory** limit/risk band; prepares the application and (within M13) records the branch-level
decision only if delegated that authority — otherwise decides nothing beyond preparation; own
recent decisions; daily collection dashboard for their own portfolio (§29).
- **Never:** sees company financials; acts on applications outside their own branch.
- **ID/selfie files are never served as static URLs.** They're stored outside the web root and
  served through an authenticated endpoint that runs through the same central tenant-scope +
  role gate as every other route (credit_officer or system_administrator, same company as the
  profile, only). A guessable/shareable file path would bypass every isolation rule in §5.

**Branch manager:** branch command dashboard (§9 of the client PRD — today's target/collected/
achievement, customers due/paid, overdue, portfolio, PAR); staff management within their branch
(view officer portfolios, allocate customers/applications, set collection targets); loan
management (review appraisal, verify documentation, approve/reject within their delegated limit,
recommend above-limit loans to the committee); portfolio management (PAR, arrears, aging,
recovery, write-offs, restructuring review) for their own branch only.
- **Never:** approves above their delegated limit without committee review; acts outside their
  own branch; disburses (that's cashier/finance).

**Loan vetting committee:** queue of applications escalated above a branch's delegated limit
(company-wide, not branch-filtered); per application — everything the branch manager saw plus the
branch manager's own decision/comments; approve/reject with required notes.
- **Never:** acts on an application no branch manager has already reviewed; sees applications
  still within a branch manager's own delegated limit (those never reach this queue).

**Cashier/finance officer:** disbursement queue (post branch-manager/committee approval);
receipts, payments, reconciliation; income/expense/penalty ledger; cashbook, income statement,
balance sheet, branch-profitability reports (§30).
- **Never:** approves or rejects a loan application; verifies KYC.

**Management:** organization-wide (their company only) monitoring and reporting — aggregates
only, no individual PII on headline screens: total disbursed, active borrowers, PAR %,
collections, revenue, disbursement trends, defaults, branch ranking, staff performance (§30).
- **MVP:** a **modular, read-only section**, built on read-only aggregate endpoints (e.g.
  `GET /portfolio/summary`), so this role can be pointed at them with no untangling — same
  pattern the earlier "Executive" concept used.

**system_administrator:** user management within their company; branch management (create/edit
branches); company-wide oversight (their queues, their loans); their audit log; configuration
(their loan products, thresholds, delegated limits); their executive/portfolio section.
"System-wide" means *their* company, not the platform.
- Admin actions logged especially carefully; admin is not a bypass around the workflow.

**super_admin platform surface:** companies list, create company + seed first
system_administrator, suspend/reactivate, per-company health/usage, cross-company overview. On
distinct `/platform/...` endpoints — the ONLY place cross-tenant access is allowed, gated
`require_role("super_admin")`.

---

## 10. Workflow Handoffs (state-driven, automatic, per company)

Handoffs are a **consequence of a status change** — no queue, no background jobs. A queue is a
filtered query over a status field (scoped by `company_id`), so **changing a status IS passing
the ball.**

- **Handoff 1 — KYC approved → customer can apply.** Means **unlock, NOT auto-submit.** Do NOT
  auto-create an application on KYC approval — the customer still chooses product + amount. When
  the credit officer sets `kyc_status = verified`, the Apply guard passes and the frontend enables
  Apply.
- **Handoff 2 — application submitted → branch manager queue.** On submit, application is written
  `status = pending`; the queue is a filtered query auto-scoped to the submitting customer's
  `branch_id` (as well as `company_id`).
- **Handoff 3 — branch manager escalates above their delegated limit → committee queue** (M13).
  Escalation is itself a status transition (`pending_branch_review` → `pending_committee_review`),
  not a separate message/notification path — same "changing a status IS passing the ball"
  principle, one level up the chain.
- **Handoff 4 — committee/branch-manager approval → cashier/finance disbursement queue** (M13/M14).

**Safety:** Apply endpoint returns `403` if `kyc_status != verified` (server-side, not just UI);
log every transition; on KYC **reject**, ball goes **back to the customer** with the reason, Apply
stays locked, they can correct and resubmit — never limbo. Built as the seam across M3–M5, and
extended through the multi-stage chain in M13.

**Every status transition is a guarded compare-and-set, not a blind write.** Approve/reject/
verify/disburse all issue `UPDATE ... WHERE id = :id AND status = :expected_status`, check the
affected row count, and reject with `409 Conflict` if it's zero. This is what makes a doubled
button-click, two officers acting on the same item, or a retried request safe by construction —
without it, a queue built on "filtered query over a status field" (as this section already
describes) can be actioned twice.

---

## 11. Status Ladders

```
Company:       active → suspended → active
Profile KYC:   pending → verified | rejected
Application:   pending → approved | rejected      (system_administrator override can reverse, with reason)
               (M13 refines "pending" into the multi-stage chain — see §26)
Loan:          approved → active → repaid         (defaulted added later; see §23 for the full
                                                     disbursement + delinquency sub-ladder)
```
Every reviewable entity carries: status enum + `reviewed_by` (FK staff user) + `reviewed_at`
+ `review_notes`.

---

## 12. Audit Trail (from day one)

- **Append-only** `AuditLog`: `company_id`, `actor`, `action`, `entity` (+ id), `timestamp`, `reason`.
- Writes on **every** review, decision, and handoff, and **especially every system_administrator
  override**.
- **Platform-level audit** for super_admin actions (create/suspend/reactivate company,
  regenerate signup code) — carries no `company_id` or a platform marker.
- **"Append-only" is enforced, not just named.** No route, service function, or admin screen ever
  issues `UPDATE`/`DELETE` against `AuditLog` — there is no code path that can, because none is
  written. On the Postgres deploy, the app's DB role additionally has no `UPDATE`/`DELETE` grant
  on the table, so even a bug can't silently rewrite history.
- **Hard rule:** a privileged action must **never** happen silently or unattributably.

---

## 13. Non-Negotiable Rules (do not violate for convenience)

1. **Tenant scoping is central and automatic.** Impossible to run a tenant query without its
   `company_id` filter. One forgotten filter = cross-company data leak = catastrophe.
2. **Backend enforces, UI reflects.** A hidden button is not access control. Scope every query by
   user + role + company on the server.
3. **Registration never accepts `role`, `company_id`, or `branch_id` from the body.** Customer via
   signup code (server resolves company); staff via admin (inherit company, `branch_id` validated
   against the admin's own company); super_admin/first-system_administrator via seed.
4. **Separation of duties holds** within each company: credit officer prepares (identity + KYC +
   appraisal), branch manager/committee decide, cashier/finance disburses — never the same person
   across two stages of one application's chain in the normal flow (§8).
5. **system_administrator override is exceptional, reasoned, and logged** — never
   routine/silent/mandatory.
6. **No unverified customer can apply** (enforced at the endpoint).
7. **Customer never sees raw credit score/scoring logic**, nor any other customer's or company's data.
8. **Credit scoring (when added) is advisory only** — informs the human, who still decides.
9. **Everything external is simulated at the start** (disbursement, repayment, notifications);
   simulated actions still write ledger + audit rows.
10. **Company suspension is manual, central, reasoned, and logged**, and cannot affect other
    companies; repayment stays open by default.
11. **Audit everything privileged** — attributable, timestamped, reasoned, at both company and
    platform tiers.
12. **The tenant-scoping mechanism is the ContextVar + SQLAlchemy event listener described in §5,
    built in M0, and proven by an automated cross-company test suite that grows with every new
    tenant-owned model.** A tenant-owned model added without an isolation test for it is an
    incomplete change, same as a decision without its audit write.
13. **Money is `Decimal`/`Numeric`, never `float`, anywhere an amount is stored or computed.**
14. **Privileged status transitions are compare-and-set** (`WHERE status = :expected`, checked row
    count), never a blind `UPDATE` — approve/reject/verify/disburse must be safe against double-
    submission and concurrent actors by construction.
15. **`User.is_active` is checked in the same central gate as company-suspension status**, every
    request — a deactivated staff account must not retain access merely because its JWT hasn't
    expired yet.
16. **KYC documents are never served from a static/guessable path.** They go through an
    authenticated, tenant-scoped, role-gated endpoint — the same enforcement as every other route.

---

## 14. Build Roadmap (milestones)

Tenancy is a **cross-cutting dimension** established early so every later milestone inherits it.
Ship **M0–M7** for a working end-to-end multi-tenant lending loop; **M8** makes it demonstrable.

**Note on role naming in the milestones below (M0–M9):** these describe work as it was actually
built, under the MVP's original role names (`company_admin`, `compliance_officer`). **M10**
renamed `company_admin` → `system_administrator` and retired `compliance_officer` (folded into
`credit_officer`) to match the client's full requirements doc — see §3, §8, §25–§31. Read
`company_admin`/`compliance_officer` below as historical; the roles in the actual codebase from
M10 onward are the ones in §3.

- **M0 — Foundation + Tenancy core.** Repo split; FastAPI + SQLModel + Alembic; SQLite; React +
  Vite + Router + TanStack Query. `Company` table (with `status` default `active`, unique
  `signup_code`, generated per the §7 entropy spec). `company_id` on every entity. **Build the
  ContextVar + SQLAlchemy event-listener tenant-scoping mechanism from §5 BEFORE any business
  logic**, and ship its automated cross-company isolation test suite in the same milestone —
  M0 is not done until that suite passes. `users` table + role enum (incl. `super_admin`) +
  `is_active`. Seed-super_admin script (CLI-only, never an HTTP route).
- **M1 — Auth + Company management.** JWT (role + company_id claims, short-lived, no refresh
  flow); login (rate-limited); `require_role`; central tenant-scope + **suspension gate + `is_active`
  check**; role/tenant-aware frontend routing. super_admin: create company + seed first
  company_admin + suspend/reactivate (+ platform audit). company_admin creates staff (inherit
  company_id). Customer self-registration **via signup code** (rate-limited endpoint; resolve →
  validate exists + active → assign customer + company_id).
- **M2 — Profile & KYC intake.** Customer profile (personal/contact/economic) + ID upload to local
  storage **outside the web root**. `kyc_status = pending`; "verification pending" banner; Apply
  disabled.
- **M3 — Compliance dashboard (KYC queue).** Pending-profiles queue (auto-scoped); per-profile
  review via the **authenticated file-serving endpoint** (never a static path); verify/reject with
  reason + reviewer fields as a **compare-and-set update**; writes audit. *(Handoff 1 seam.)*
- **M4 — Loan products & application.** Seed 2–3 products per company (Salary Advance, Emergency,
  Business). Verified customers apply; application → `pending`. Apply guard = KYC verified +
  company active. No auto-scoring.
- **M5 — Credit officer dashboard (approval queue).** Pending-applications queue; per-application
  view; approve/reject with required notes as a **compare-and-set update**; approval generates
  repayment schedule (`Decimal`/`Numeric` amounts) + activates loan. *(Handoff 2 seam.)*
- **M6 — Customer dashboard.** Limit, active loans, status, repayment schedule, transaction history,
  application status (with rejection reason), simple standing indicator (not raw score).
- **M7 — Disbursement & repayment (simulated).** "Disburse" marks active + writes ledger row (no
  real money). Repayment form records payments against schedule; **repayment endpoints are on the
  suspension allow-list**. In-app notifications only.
- **M8 — Admin/platform dashboards + override + portfolio.** company_admin user management +
  company-wide oversight + audit log + explicit **override action** (separate, reason-required,
  distinctly logged) + read-only portfolio section (modular aggregate endpoints). super_admin
  platform dashboard (companies, status, cross-company overview).

**Deferred (post-MVP):** rule-based credit scoring (advisory); OTP/SMS/WhatsApp; real M-Pesa/bank
integrations; biometrics; CRB/bank-statement analysis; financial literacy academy; HR & full
accounting; billing/plans/usage-caps/auto-suspension; subdomains-as-product & per-tenant theming;
splitting system_administrator into a technical System Administrator + senior business role (§8);
PostgreSQL RLS hardening; heavier per-tenant isolation for large regulated clients.

### M10–M19 — Reconciling the client's full requirements doc

Triggered by the client handing over their full PRD (branch-based MFI operations, not a generic
multi-company SaaS shape). Architectural decisions behind this phase are recorded in §3 (roles),
§5 (Branch vs. company isolation), and §8 (the multi-stage approval chain). Every milestone below
that adds a `TenantMixin` model must extend `tests/test_tenant_isolation.py` in the same change
(rule #12) — stated once here rather than repeated per bullet.

- **M10 — Role & Branch foundation.** `Branch` entity (company-scoped, §25). `UserRole` becomes
  `super_admin, system_administrator, credit_officer, branch_manager, loan_vetting_committee,
  cashier_finance_officer, management, customer` — `company_admin` renamed to
  `system_administrator`; `compliance_officer` retired (its endpoints now gated on
  `credit_officer`). `User.branch_id` added (required for `credit_officer`/`branch_manager`).
  Staff creation validates `branch_id` belongs to the creating admin's own company. Minimal
  `Branch` CRUD for `system_administrator`. Isolation suite extended for `Branch`.
- **M11 — Extended customer registration + Business Assessment.** Full client PRD §2A/§2B field
  set on `Profile` (or a linked entity): 3 names, ID/passport, DOB, gender, nationality, marital
  status, dependants, phone numbers, residence, next of kin, referees, employment/business info,
  photo, supporting documents, generated customer number. New `BusinessAssessment` entity
  (business name/type/ownership/location/years in operation/sales/expenses/profit/stock value/
  existing loans/other lenders/bank-Mpesa turnover/assets/cash-flow) with server-computed
  `net_income = total_income - total_expenses` and
  `debt_service_capacity = available_income - existing_debt_obligations` (§27).
- **M12 — Guarantors & Securities.** `Guarantor` entity (full name, ID number, telephone,
  occupation, residence, relationship, guaranteed amount, signature/consent, verification status)
  and `Security`/collateral entity, both scoped to `LoanApplication`. Submission is blocked
  server-side while mandatory guarantor fields are incomplete (§27).
- **M13 — Multi-stage approval workflow.** `LoanApplication` status ladder becomes
  `pending_branch_review → [pending_committee_review] → pending_finance_review → approved |
  rejected`, driven by each product/branch's delegated limit. New append-only per-stage review
  record (stage, actor, decision, comments, timestamp). No-self-approval check enforced at every
  stage transition (§8, §26).
- **M14 — Disbursement module extension.** Capture approved amount, account/M-Pesa details, bank,
  branch, disbursement date, fees, net amount, loan number, disbursement reference (idempotent);
  ladder `Pending → Approved → Ready for Disbursement → Disbursed`, reconciled with the existing
  §23 sub-states (§28).
- **M15 — Collections & Arrears.** System-computed Days Past Due and aging buckets (current,
  1–7, 8–30, 31–60, 61–90, 90+); PAR = outstanding **principal** of loans in arrears / gross
  outstanding **principal** portfolio × 100 (correcting the M8 portfolio-summary PAR, which used
  full outstanding balance — see §29); Daily Collection Dashboard; payment recording + receipts;
  `CollectionAction` log (call/reminder/promise-to-pay/visit/escalation) (§29).
- **M16 — Field Collections.** Mobile "My Collection Route" view (today's due customers,
  call/directions/record-payment/promise-to-pay/visit-report actions); optional GPS/time capture
  on `CollectionAction`, consent-gated (§29).
- **M17 — Financial Module.** Income (interest/fees/penalties/other) and `ExpenseEntry` (salaries/
  rent/transport/comms/admin/other) tracking; cashbook, income statement, balance sheet, branch
  profitability — all derived read-only from `Transaction` + `ExpenseEntry`, never a second
  ledger (§30).
- **M18 — Management Reporting.** Parameterized aggregate report endpoints (date-range +
  granularity, not one endpoint per cadence) covering the client PRD's daily/weekly/monthly report
  set (§30).
- **M19 — Frontend dashboard build-out.** Per-role dashboards for `branch_manager` (the exact
  "Good Morning" daily-target layout from the client PRD), `loan_vetting_committee`,
  `cashier_finance_officer`, `management`; `system_administrator` branch/staff management UI;
  customer portal polish against §31's menu mapping.

---

## 15. Core Entities (to be modelled in M0)

`Company` (status, signup_code), `User` (role, company_id, `is_active`), `Profile` (company_id,
KYC status + reviewer fields), `LoanProduct` (company_id), `LoanApplication` (company_id, review
fields), `Loan` (company_id), `RepaymentSchedule` (company_id, `Decimal`/`Numeric` amounts),
`Transaction` (company_id, `Decimal`/`Numeric` amounts), `AuditLog` (company_id nullable for
platform actions). All status enums, reviewer fields, the override-aware audit structure, and
`company_id` are wired from M0.

---

## 16. How to work in this repo (for the AI assistant)

- Implement **one milestone at a time**, in order. Do not scaffold deferred features.
- **Tenancy first:** never write a tenant query that isn't routed through the central scoping
  mechanism. If you find yourself typing `WHERE company_id` by hand in a route, stop — put it in
  the central layer instead.
- **Adding or touching a tenant-owned model requires adding/extending its cross-company isolation
  test in the same change** (see §5). Not optional, not a follow-up PR.
- For any endpoint touching data: add the `require_role` guard, ensure the tenant scope applies,
  and (for staff decisions) write the matching **audit entry** in the same change. An action
  without its audit write is incomplete.
- **Any endpoint that changes a status** (approve/reject/verify/disburse/override) writes its
  update as a compare-and-set (`WHERE status = :expected`) and returns `409` on a mismatch — never
  a blind `UPDATE`. Same "incomplete without it" standard as the audit write.
- Registration/creation code must derive `role`, `company_id`, and `branch_id` server-side — never
  from the request body except as a branch *choice* that is then validated against the creating
  admin's own `company_id` before being trusted.
- Keep customer-facing responses free of internal fields (scores, notes, reviewer identities,
  anything cross-company).
- Honor the suspension gate centrally; keep the repayment allow-list explicit. The same gate checks
  `User.is_active`, not company status alone.
- File-backed resources (KYC ID/selfie) are always served through an authenticated, tenant-scoped
  route — never a static URL a session cookie or bearer token doesn't gate.
- Monetary values are `Decimal` end to end — in Python, in the DB column type, and in any
  intermediate calculation. Never cast to `float`.
- Mirror Pydantic request/response models with Zod on the frontend where forms are involved.
- This is a financial, multi-tenant app — favor correctness, isolation, and traceability over
  cleverness or brevity.

---

## 17. Signup Code — Auto-Assignment (clarified)

The customer NEVER types the code on the happy path — the entry point carries it.

- Company shares a dedicated link: `yourplatform.com/apply/ABC-K3F9` (or subdomain
  `abc.yourplatform.com`). The code lives in the URL.
- Frontend reads the code from the route param on page load and holds it in form
  state / a hidden field. The signup form shows NO company-code input.
- Persist the code across the flow (app state or the register-route query) so a
  refresh or navigation doesn't lose it.
- On page load, quietly validate the code via a lightweight public endpoint that
  returns ONLY the company's display name + active status (nothing sensitive). If it
  fails, show "This signup link is invalid or no longer active" BEFORE the user fills
  the form.
- Show the resolved company name as confirmation: "Create your account with Company ABC."
- On submit, frontend sends the code + the user's own details. Server resolves
  code -> company, validates exists + active, stamps company_id + role=customer.
- Manual "Company code" field exists ONLY as a fallback for users who land on the
  bare signup page without a code. Never shown on the happy path.

---

## 18. Frontend & UX Conventions

One consistent SHELL (layout + nav + components) that adapts its CONTENTS per role.
A customer, an officer, and an admin feel like one well-built product, seeing
different things. Consistency > novelty (a financial app earns trust by feeling
orderly and predictable).

### Persistent shell (every authenticated page)
- **Left sidebar (side nav):** vertical, fixed on desktop, collapsible to icons,
  hamburger drawer on mobile. Holds primary nav for that role; highlights the active
  section; logo at top; user identity + role + logout at bottom.
- **Top bar (header):** thin, persistent. Left: page title / breadcrumb. Right:
  notifications bell, user avatar/menu, and current company label (for staff) or a
  "viewing: [Company]" indicator (super_admin drilling in).
- **Main content area:** consistent max-width + comfortable padding; never edge-to-edge.
- **Responsive grid:** content on cards (div panels, subtle border/shadow, rounded
  corners); 1 column mobile, multiple desktop.

### Shared component vocabulary (use shadcn/ui or Mantine; reuse everywhere)
- **Stat cards:** labelled number + icon (e.g. "Active Loans: 3") on every dashboard.
- **Data tables:** every queue/list. Sortable headers, status badges, row actions,
  pagination, filter/search bar, empty states.
- **Status badges:** colour-coded pills, SAME colours everywhere — pending=amber,
  approved/verified=green, rejected=red, active=blue. Never colour alone (badge text too).
- **Buttons:** clear hierarchy — one primary per screen (e.g. "Approve"), secondary for
  lesser actions, red destructive for reject/suspend. Never two competing primaries.
- **Forms:** consistent fields, inline Zod validation messages, clear submit,
  disabled/loading states.
- **Modals / drawers:** for review actions (approve/reject + reason) so the officer
  stays in context.
- **Toasts:** brief confirmations after actions ("Loan approved").
- **Loading skeletons + empty states:** skeleton while TanStack Query fetches; friendly
  empty state ("No pending applications") instead of a blank void.

### Per-role nav + dashboard contents (same shell, different contents)
- **Customer** — nav: Dashboard, My Loans, Apply, Repayments, Profile. Dashboard: stat
  cards (available limit, active loans, next payment due), repayment-schedule card,
  recent transactions table, KYC/application status banner, prominent Apply button
  (disabled until verified, tooltip explains why).
- **Credit officer** — nav: Dashboard, Customers (registration + KYC queue), Applications,
  Collections, My Decisions. Dashboard: stat cards (pending KYC, pending applications, today's
  collections), KYC/applications queue tables; row -> review drawer (profile + income/expenses +
  documents + guarantors + later advisory score) + verify/approve/reject-plus-notes.
- **Branch manager** — nav: Dashboard, Staff, Applications (escalation queue), Portfolio,
  Collections. Dashboard: the client PRD's daily-target layout (§26, §29) — target/collected/
  achievement, customers due/paid, overdue, portfolio, PAR — plus a Loans-Beyond-Limit queue.
- **Loan vetting committee** — nav: Dashboard, Committee Queue, My Decisions. Dashboard: stat
  cards (pending committee review, decided today); queue table with the branch manager's prior
  decision visible; row -> review drawer + approve/reject-plus-notes.
- **Cashier/Finance officer** — nav: Dashboard, Disbursements, Financials (cashbook, income
  statement, balance sheet), Reports. Dashboard: stat cards (pending disbursement, today's
  receipts, today's expenses); disbursement queue; financial report drill-downs.
- **Management** — nav: Dashboard, Reports, Branch Ranking, Staff Performance. Dashboard:
  aggregates only (§9, §30) — portfolio, PAR, collections, disbursement trend, branch ranking.
- **System administrator** — nav: Dashboard, Users, Branches, Applications, Loans, Products,
  Portfolio, Audit Log, Company Profile.

---

## 19. Lending Features to Add (grounded in 2026 loan-platform practice)

Adopt the IDEA now in its simplest form; defer the heavy/AI version. All per-company (tenant-scoped).

- **Collections / delinquency stage.** Extend the loan ladder to
  `active → overdue → defaulted` and add a **collections queue** for staff (overdue loans).
  This is the natural home for reminders later. Cheap now, expected by modern systems.
- **Admin-configurable loan products.** Products (interest, term, limits, eligibility rules)
  are **data rows a system_administrator edits**, NOT values hard-coded in the app. Configuration-first.
  Each company configures its own products.
- **Compliance-native, not bolt-on.** Already have audit logs + RBAC. Add **light real-time
  exception monitoring**: flag anomalies (e.g. many rapid applications from one customer, an
  officer approving unusually fast) onto a review/exceptions list.
- **Borrower transparency as a feature.** Show a **repayment/amortization breakdown**
  (principal vs interest per installment, not just "amount due") and **loan terms upfront**
  before the customer accepts. Transparency is a product feature, enforced by the system.
- **Security posture (design toward it, don't certify yet).** Target = SOC 2 Type II-style:
  encryption at rest for KYC documents, documented access controls, a data-retention policy.
  Name it now to avoid corner-painting.

**Still deferred (the "AI era" layer):** AI/automated decisioning, embedded lending,
predictive analytics. Wrong for MVP (paid-service, high-complexity). The rule-based advisory
score remains the correct first step; architecture leaves the door open.

**Short list to fold into the roadmap/data model now:** delinquency stage + collections queue;
admin-configurable products; amortization breakdown for borrowers; upfront term transparency;
light anomaly/exception flag list.

---

## 20. Admin Dashboard — Modern & "Lively" (2026 design consensus)

Governing idea: a dashboard is a COCKPIT, not a report. Every element must earn its pixel by
helping someone decide or act. "Lively" = clarity + motion + hierarchy, NOT gradients/clutter.

### Principles
- **One verdict per screen.** Decide the single number/status the user came for; give it the
  top-left slot and the largest type. Everything else supports it. (Admin hero = Portfolio-at-Risk %
  or total active portfolio.)
- **Capped KPI strip: 4–6 cards**, each with ONE comparison (trend vs last period) and ONE visual
  (sparkline). Resist adding more. (E.g. total disbursed, active borrowers, PaR%, collections rate.)
- **Hierarchy from type + space, not boxes.** Draw few borders (à la Linear/Stripe/Mercury);
  weight, size, whitespace do the grouping. Drop heavy borders + ornamental shadows. Protect
  the data-ink ratio.
- **Progressive disclosure.** High-level summaries first, trends second; hide granular tables
  behind drill-downs / modal drawers. No raw table dumps on the summary.
- **Color means state, consistently.** Reserve red/green strictly for loss/gain
  (overdue/healthy, rejected/approved). Never decorative — dovetails with the status-badge system.
- **Three states per component:** loading (skeleton), empty (friendly), error. Chart colors from
  the token system, WCAG-contrast verified.

### Layout skeleton (proven pattern — adopt wholesale)
- Sidebar **240–280px**, collapsing to a **64px icon rail**.
- **4–6 card** metric strip.
- **12-column CSS Grid** content area, `auto-rows: minmax(200px, auto)`.

### Dark mode = first-class
- A 2026 baseline. Build light/dark **design tokens from the start** (don't retrofit). Dark mode
  changes elevation (lighter = closer), chart palettes, and contrast math — it's not just a skin.

### Where "lively" actually comes from (motion, not ornament)
- Subtle count-up on KPI numbers, smooth chart transitions, skeleton shimmer, row hover states,
  toast slide-in on actions. Small, purposeful animation reads as modern; heavy ornament reads dated.

### The test for every element
- "Would users notice if this disappeared tomorrow? If not, cut it." Density with discipline
  beats decoration.

---

## 21. Per-Company Profile & Branding (tenant customization)

Super admin stamps a company's identity at CREATION; system_administrator maintains the
client-facing subset later. Same pattern as everywhere: the tier above creates, the tier below
maintains within bounds. This is tenant customization, NOT a theming engine.

### Who does what
- **super admin (at company creation):** sets name, contacts/address, and theme colors — company
  creation now captures profile + branding, not just name + signup_code.
- **system_administrator (later):** edits the client-facing subset (contacts, address, logo,
  brand colors). Cannot touch signup-code policy, plan, or anything platform-level.

### What the profile holds (on `Company` or a linked `CompanyProfile`)
- **Identity:** display name, legal name (optional), logo, tagline/motto.
- **Contacts / address:** support phone, support email, physical address, business registration
  number. Feeds customer-facing UI ("Contact your lender" shows THEIR details) and documents.
- **Branding / theme:** a SMALL set of brand tokens only (see below).

### Theme colors — the right way (keeps it trivial & safe)
- Store only a HANDFUL of values per company: primary/brand color, optional accent, logo.
- The frontend already uses **design tokens** (§18/§20). Per-tenant branding = **override a few
  token values with the company's colors at load time.** Layout, spacing, components, dark-mode
  math stay identical and platform-controlled.
- Principle (same as signup code): **tenant supplies DATA (a color, a logo); the platform controls
  the MECHANISM.** Companies never write CSS or get custom layouts.

### Guards
- **Validate colors:** accept hex; check contrast (ties to §20 WCAG rule) so a brand color can't
  make button text unreadable — auto-adjust text color or warn at creation.
- **Sensible defaults:** no colors supplied → fall back to platform default theme. Branding is
  optional polish, never required to function.
- **Dark mode still works:** brand color sits on top of the light/dark elevation system; test the
  primary on both.

### Where it surfaces (and where it must NOT)
- Shows on the company's own surfaces: that company's login/signup page (already shows company name
  from signup-code work — now + logo + brand color), customer dashboard, top bar, later
  emails/documents. A Company-A user sees Company-A identity throughout.
- **Scoped by `company_id`** like all tenant data — resolved from the tenant; one company's
  branding must NEVER surface in another's context. Cosmetic, but rides the same isolation rules.
- **super admin platform console stays on neutral platform branding** — never reskins per company,
  so you always know which tier you're operating in.

### NOT in scope
Not custom CSS, not per-tenant layouts, not a theme builder. A few brand tokens + logo + contact
fields, applied through the fixed design system. That's the whole feature.

### Roadmap placement
- **Data model:** extend `Company` (or add `CompanyProfile`) — identity, contacts/address, brand
  tokens (primary color, accent, logo reference).
- **M1:** super admin create-company form captures name + contacts/address + theme colors;
  system_administrator gets an edit view for the client-facing subset.
- **Frontend:** token system gains a per-tenant override step — on load, resolve company, merge
  its brand tokens over defaults. Everything else unchanged.

---

## 22. Notification / Messaging Module — abstraction-first

> Payment-gateway integration (Daraja/M-Pesa) is explicitly OUT of scope for now — it stays
> inside the "zero external paid services at the start" constraint from §1. Disbursement and
> repayment remain simulated (§23's ladder adds sub-states for realism, not a real gateway).

A SECOND CONSUMER of existing state transitions + audit (registration success/fail, KYC verified/
rejected, loan approved/denied/disbursed, payment due/received, overdue).
- **Single `notify(user, event, data)`** with a `NotificationChannel` interface. Business logic never
  calls a vendor directly.
- **Now (zero cost):** in-app (Notification row, §18 bell) + email (free-tier / console in dev).
- **Later (drop-in):** SMS (e.g. Africa's Talking) + WhatsApp behind the same interface.
- **Per-company:** channels, sender IDs, TEMPLATES (event universal, wording/branding per tenant, §21).
- **Don't over-engineer:** module inside FastAPI (sync / APScheduler for reminders). NO queue/bus/
  separate service at MVP.

---

## 23. Loan Calculation Engine + Interest Models + Penalties

THE money-critical module. "Roughly right" is unacceptable.

### Core principles
- **One backend module = single source of truth** (`loan_calculation`). Never scatter money math;
  never duplicate on frontend.
- **Frontend NEVER computes real money.** Calculator widget may PREVIEW; actual balance/interest/
  schedule computed + stored SERVER-SIDE. Frontend displays server values.
- **Decimal only, never float.** Money as integer-cents / Decimal columns. One explicit rounding rule
  (half-up, to the cent).
- **Heavily unit-tested** — first module to get real tests; each interest model tested separately.

### Interest models — ALL THREE, selected by loan type (strategy pattern)
- `LoanProduct.interest_model` ∈ { `flat`, `reducing_balance`, `daily_accrual` } + rate + period.
  Per-product AND per-company.
- One impl per model behind a shared interface; one dispatcher picks by product. System calls the
  dispatcher, never a specific model. 4th model later = new impl + register.
  - `flat`: principal × rate, fixed.
  - `reducing_balance`: interest on shrinking balance (amortized).
  - `daily_accrual`: per-day on outstanding (short-term/salary advance).
- Unsure for a product -> `flat` (simplest/most transparent); others available per product.

### Penalties — separate, explicit, capped, audited
- Total owed = principal + base interest (model) + penalties (rule). Shown as a 3-way BREAKDOWN, never
  one opaque number.
- Per-product config: `penalty_type`, `penalty_rate/amount`, `grace_period_days`, `penalty_cap`.
- Tie to `overdue`; applied by the APScheduler due-date scan; EACH application is its own ledger/audit
  entry. Owed amount never grows silently.

### DEV PLACEHOLDER FIGURES — **NOT FINAL. To be revised by FINANCE after review.**
> Development placeholders only. Live as per-product CONFIG (not hard-coded), so Finance's revised
> numbers are a config change, not code.
- **Penalty rate: 1% per day** on the overdue amount. *(DEV placeholder.)*
- **Grace period: 3 days** — penalties begin day 4 (due_date + 3); per-product, default 3. *(DEV placeholder.)*
- **Penalty cap: 100% of principal** (interest + penalties ≤ principal); accrual STOPS at the ceiling.
  *(DEV placeholder — MUST confirm current CBK DCP cap before production.)*
- **WARNING:** 1%/day (~30%/month) UNCAPPED is runaway/predatory — exactly what CBK regulates. The cap
  is the safety mechanism. The job checks the cap before applying each day's penalty and stops at the limit.
- Grace delays when PENALTIES start; decide separately whether it delays `overdue` for PaR (recommend:
  internal "past due" day+1, borrower-facing `overdue` + penalties day+4).

### The six dashboard items (all derived)
1. **Loan owed** = server-computed balance (principal + interest + penalties), shown as breakdown.
2. **Loan paid** = sum of repayment Transaction rows.
3. **Loan history** = customer Loan rows + per-loan Transaction history (table + badges).
4. **Loan rate (daily/weekly/monthly)** = LoanProduct config; period conversions in the module.
5. **Repayments** = RepaymentSchedule (generated at approval) + repayment processing (reduces balance,
   simulated — no real payment gateway at MVP, see §1).
6. **Due dates** = RepaymentSchedule dates (disbursement date + product term/frequency).
- Two faces, same math: interactive CALCULATOR (preview, non-binding) vs SERVICING calcs (stored truth).

### Updated loan ladder
```
approved → disbursement_pending → disbursing → disbursed/active → repaid
                                        └→ disbursement_failed
   active → overdue → defaulted
```
Disbursement sub-states model realistic failure/retry even though disbursement stays simulated
(no real gateway yet, §1) — `disbursement_failed` is reachable from a simulated failure path so
the state machine and its audit trail are proven before a real gateway ever plugs in.

---

## 24. Updated Core Entities & Config Fields (supersedes/extends §15)

- `Company`: status (active/suspended), signup_code (unique), + `CompanyProfile` (identity, contacts/
  address, brand tokens), + per-company settings (onboarding-fee on/off/amount/refundable,
  auto-disburse on/off, large-loan threshold, notification channel/template config).
- `Branch`: company_id, name, code (unique per company), address, manager_id (FK user), is_active.
  See §25 — a company-scoped org unit, NOT a tenant boundary.
- `User`: role (super_admin/system_administrator/credit_officer/branch_manager/
  loan_vetting_committee/cashier_finance_officer/management/customer), company_id (null for
  super_admin), branch_id (required for credit_officer/branch_manager, optional otherwise, null
  for super_admin).
- `Profile`: company_id, KYC status + reviewer fields, (optional) payment_pending state if onboarding fee enabled.
  Extended per §26 with the client PRD's full registration/business-assessment field set (M11).
- `Guarantor`, `Security` (collateral): company_id, application_id — see §27.
- `BusinessAssessment`: company_id, application_id (or profile_id) — see §27.
- `LoanProduct`: company_id, interest_model, rate, period, term, limits, eligibility rules,
  penalty_type, penalty_rate (DEV 1%/day), grace_period_days (DEV 3), penalty_cap (DEV 100% principal),
  branch_manager_delegated_limit (§26).
- `LoanApplication`: company_id, branch_id, review fields (status, reviewed_by, reviewed_at,
  review_notes), recommended_amount. M13 adds a per-stage review trail — see §26.
- `Loan`: company_id, branch_id, disbursement sub-states + delinquency states, computed/stored
  balance fields (principal outstanding, accrued interest, penalties), disbursement ref
  (idempotency), disbursement account/bank/M-Pesa details (§28).
- `RepaymentSchedule`: company_id, installments with due_dates, amounts (principal/interest split).
- `Transaction`: company_id, type (disbursement/repayment/penalty/fee), amount (Decimal/cents), ref, timestamp.
- `CollectionAction`: company_id, loan_id, actor, type (call/reminder/promise_to_pay/field_visit/
  escalation), notes, gps/time (optional, privacy-guarded) — see §29.
- `AuditLog`: company_id (nullable for platform actions), actor, action, entity+id, timestamp, reason.
- `Notification`: company_id, user, event, channel, status, timestamp.

All money = Decimal/integer-cents. All financial config = per-product/per-company (Finance-revisable).

---

## 25. Branches (organizational unit, not a tenant boundary)

Grounds §3/§5's Branch summary in one place. A `Branch` is how one company (tenant) organizes
its own staff and portfolio — the client PRD's whole operating model is branch-based, so this is
core, not cosmetic.

- **Fields:** `company_id`, `name`, `code` (unique per company — short, human-referenceable, e.g.
  `NRB-01`), `address`, `manager_id` (FK `user.id`, the branch's `branch_manager` — optional so a
  branch can exist before its manager is hired), `is_active`.
- **Who creates/edits:** `system_administrator` only, within their own company (`POST/PATCH
  /admin/branches`). No signup-code-style self-service — branches are internal org structure, not
  a tenant-facing concept.
- **Isolation:** `Branch` inherits `TenantMixin` like everything else — `company_id` is enforced
  by the central mechanism (§5), and it is covered by the cross-company isolation suite like any
  other tenant-owned model (rule #12). `branch_id` itself is never a security boundary — see §5's
  explicit callout of the asymmetry with `company_id`.
- **Who is scoped to a branch:** `credit_officer` and `branch_manager` require a `branch_id`
  (their queues, portfolios, and daily dashboards filter on it). `loan_vetting_committee`,
  `cashier_finance_officer`, `management`, and `system_administrator` default to company-wide
  (`branch_id = null`) since the PRD's own descriptions of those roles are company/region-wide,
  not single-branch (§3).
- **Customers:** a customer is registered by a specific branch's credit officer; recording the
  customer's `branch_id` at registration is part of M11 (extended registration), not M10 — M10
  only adds the column to `User` for staff.

---

## 26. Multi-Stage Loan Approval & Delegated Limits (client PRD §5, §11–§12)

Builds on §8 and §10. Concrete state machine for **M13**:

```
submitted
  → pending_branch_review
      → approved | rejected                              (amount ≤ branch's delegated limit)
      → pending_committee_review                          (amount > branch's delegated limit)
          → approved | rejected
  → [if approved] pending_finance_review                   (cashier/finance sign-off, §28)
      → ready_for_disbursement → disbursed
```

- **Delegated limit config:** `LoanProduct.branch_manager_delegated_limit` sets the default;
  `Branch` may carry its own override (a larger or smaller branch may be trusted with a different
  limit). The **effective limit for a given application is `min(branch override, product
  default)`** if both are set — never silently take the larger, looser figure.
- **Per-stage review record (new entity, e.g. `ApplicationReviewStage`):** `application_id`,
  `stage` (`branch_review` / `committee_review` / `finance_review`), `actor_id`, `decision`
  (approve/reject), `comments` (required — mirrors the existing credit-officer "required notes"
  convention), `decided_at`. **Append-only** — a later override still goes through the
  `system_administrator` override path (§8), never by editing a stage record.
- **No-self-approval (client PRD §5):** before writing any stage's decision, check the acting
  user's id does not appear as `actor_id` on any earlier stage of the same application (or as the
  application's own `reviewed_by`/preparer where that's tracked). Reject with `403` if it does —
  this is a hard rule, not advisory.
- **Compare-and-set throughout:** every stage transition is `WHERE status = :expected_status`
  (rule #14) exactly like the existing single-stage approve/reject.
- **Rejection at any stage ends the chain immediately** — ball goes back to the customer/credit
  officer with the reason (same "never limbo" principle as §10's KYC-reject handoff), not forward
  to a later stage.

---

## 27. Guarantors, Securities & Business Assessment (client PRD §2B, §4)

**Business Assessment (M11)** — captured by the credit officer alongside the loan application:
business name, type, ownership, physical location, years in operation, daily/weekly/monthly
sales, expenses, profit, stock value, existing loans, other lenders, bank/M-Pesa turnover (only
where the customer has authorized it), business assets, cash-flow assessment. The system
**always computes**, never accepts as free-entry:
- `net_income = total_income - total_expenses`
- `debt_service_capacity = available_income - existing_debt_obligations`

Both computed server-side in one place (mirrors §23's "one backend module = single source of
truth" principle for loan math) — never recomputed ad hoc in a router or on the frontend.

**Guarantors (M12)** — each `Guarantor` row: full name, ID number, telephone, occupation,
residence, relationship to applicant, guaranteed amount, signature/consent (a stored
attestation, not a raw image requirement at MVP), verification status. **A loan application
cannot be submitted while mandatory guarantor fields are incomplete** — enforced at the submit
endpoint (`403`, same pattern as the existing KYC-verified Apply guard in §10), not just a
frontend form validation.

**Securities/collateral (M12)** — a `Security` row per pledged asset tied to the application:
description, estimated value, and (later) a document reference. Optional per product/policy —
not every loan requires collateral.

---

## 28. Disbursement Module (extended) (client PRD §6)

Extends the existing simulated-disbursement flow (§23, M7) with the fields the client PRD
requires captured at disbursement time: approved amount, customer name (denormalized for the
disbursement record), account/M-Pesa details, bank, branch, disbursement date, fees, net amount
disbursed, loan number, disbursement reference (the existing idempotency key, §23).

Ladder (client PRD's own wording, reconciled with the existing §23 sub-states):
```
Pending → Approved → Ready for Disbursement → Disbursed
(approved)  (pending_finance_review cleared)   (cashier/finance executes; still simulated, §1)
```
`cashier_finance_officer` is the actor who moves `Ready for Disbursement → Disbursed` — not
`credit_officer`, which is who executes it under the current M7 implementation. This is the one
concrete permission change M14 must make (today's `POST /credit/loans/{id}/disburse` role gate
moves to `cashier_finance_officer`). Still fully simulated per §1 — no real gateway — but still
writes a ledger + audit row (rule #9).

---

## 29. Collections, Arrears & Field Collections (client PRD §7–§8, §13)

**Days Past Due (DPD) and aging** — DPD is computed the same way delinquency already is
(`app/loan_delinquency.py` — extend, don't duplicate) from the earliest unpaid installment's due
date. Classify into the client's exact buckets: **current, 1–7, 8–30, 31–60, 61–90, 90+ days**.

**Portfolio at Risk — corrected formula.** The client PRD's formula is explicit:
```
PAR = outstanding PRINCIPAL of loans in arrears / gross outstanding PRINCIPAL portfolio × 100
```
The current M8 `GET /admin/portfolio/summary` computes PAR using `outstanding_balance` (which
includes accrued interest and penalties, per `models/loan.py`), not principal alone. **M15 must
add a stored/derived outstanding-principal figure** (principal minus principal actually repaid,
distinct from the interest/penalty-inclusive `outstanding_balance`) and recompute PAR from it —
this is a required correction, not a style choice, since it's the number Management and
regulators actually read.

**Daily Collection Dashboard** (credit officer + branch manager, filtered to their own portfolio/
branch respectively): today's collections, amount due today, amount collected, outstanding
amount, number of customers due, number paid, number partially paid, number unpaid. Status pills
— 🟢 Paid / 🟡 Partially Paid / 🔴 Overdue — follow the existing colour-coded badge convention
(§18: colour + text, never colour alone).

**Collection actions** — `CollectionAction` entity (`loan_id`, `actor_id`, `type`: call /
reminder / promise_to_pay / field_visit / escalation / note, `notes`, `created_at`). "Record
payment" and "issue receipt" stay on the existing `Transaction` ledger (a receipt is a formatted
view of a repayment `Transaction`, not a new source of truth for money).

**Field Collections (M16)** — a mobile-friendly "My Collection Route" view: today's due customers
with per-customer actions (Call, Directions, Record Payment, Promise to Pay, Visit Report).
**GPS/time capture is optional and consent-gated** — request device location permission
explicitly and only when a field visit is being logged, never silently in the background; store
it on the relevant `CollectionAction` row, scoped and access-controlled exactly like every other
tenant-owned record.

---

## 30. Financial Module & Management Reporting (client PRD §14–§15)

**Financial Module (M17)** — `cashier_finance_officer` sees income (interest, fees, penalties,
other approved income — all already itemized on `Transaction`) and a new `ExpenseEntry` ledger
(salaries, rent, transport, communications, administration, other), both `company_id`- and
optionally `branch_id`-scoped. Reports — cashbook, income statement, balance sheet, loan
portfolio report, collection report, disbursement report, outstanding balances, branch
profitability — are **all derived, read-only views over `Transaction` + `ExpenseEntry`**, never
a second ledger that could drift from the real one.

**Management Reporting (M18)** — the client PRD's daily/weekly/monthly report set (collections,
disbursements, arrears, cash, officer performance / portfolio performance, PAR, recovery, branch
ranking, new customers / profitability, portfolio growth, collection efficiency, loan aging,
product performance, staff performance) is built as **parameterized aggregate endpoints** (a
date-range + granularity parameter), not one hand-written endpoint per cadence — same "one
dispatcher, selected by a parameter" philosophy §23 already uses for interest models.

---

## 31. Customer Portal & Core System Menu (client PRD §16–§17)

The client PRD's customer portal (loan balance, next installment, repayment schedule, payment
history, loan status, receipts, application status) is already substantially covered by the
existing customer dashboard (§9, M6) — M19 is a verification/polish pass against the PRD's exact
list, not a rebuild.

The client PRD's menu (`Dashboard / Customers / Loans / Repayments / Collections / Guarantors /
Securities / Branch Management / Staff / Finance / Reports / Notifications / System
Administration`) maps onto this project's existing per-role nav convention (§18) rather than a
single shared menu — each role's `NAV_BY_ROLE` entry (§18) surfaces only the subset of that menu
relevant to their job, per §9's data-scope principle. No new "one true nav" structure is needed;
M19 extends `NAV_BY_ROLE` role-by-role as each milestone's pages ship.
