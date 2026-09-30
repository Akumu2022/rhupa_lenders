import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Card, EmptyState, HeroStat, LinkTile, PageHeader, SectionLabel, StatCard } from "../../components/ui";
import type { CompanyResponse } from "../../schemas/company";

// Mirrors backend app/routers/platform_security.py.
interface DatabaseSecurity {
  database: string;
  role: string | null;
  role_bypasses_rls: boolean | null;
  enforced: boolean;
  tables: { table: string; has_policy: boolean; rls_enabled: boolean; rls_forced: boolean; owned_by_app_role: boolean }[];
}

/** Is Postgres itself enforcing company separation (row-level security)?
 * The database-level backstop behind the app's own tenant filter. */
function DatabaseSecurityCard() {
  const query = useQuery({
    queryKey: ["platform", "security"],
    queryFn: () => apiRequest<DatabaseSecurity>("/platform/security"),
  });
  const s = query.data;
  if (!s) return null;
  // A rule binds the app's role once enabled if the role doesn't own the
  // table; an owner is bound only when the rule is forced.
  const binding = s.tables.filter((t) => t.has_policy && t.rls_enabled && (t.rls_forced || !t.owned_by_app_role)).length;
  const withPolicy = s.tables.filter((t) => t.has_policy && t.rls_enabled).length;
  return (
    <Card className="mt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SectionLabel>Database-level company separation</SectionLabel>
        {s.enforced ? (
          <Badge tone="success">Enforced by the database</Badge>
        ) : (
          <Badge tone="warning">App-level only</Badge>
        )}
      </div>
      {s.database !== "postgresql" ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Not applicable on {s.database} (development database).</p>
      ) : (
        <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-slate-500 dark:text-slate-400">App database role</dt>
            <dd className="font-medium text-slate-900 dark:text-slate-50">
              {s.role} {s.role_bypasses_rls ? <Badge tone="danger">bypasses RLS</Badge> : <Badge tone="success">subject to RLS</Badge>}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500 dark:text-slate-400">Tables with the separation rule</dt>
            <dd className="font-medium tabular-nums text-slate-900 dark:text-slate-50">{withPolicy} / {s.tables.length}</dd>
          </div>
          <div>
            <dt className="text-slate-500 dark:text-slate-400">Tables where it is enforced</dt>
            <dd className="font-medium tabular-nums text-slate-900 dark:text-slate-50">
              {s.role_bypasses_rls ? 0 : binding} / {s.tables.length}
            </dd>
          </div>
        </dl>
      )}
    </Card>
  );
}

export function PlatformDashboardPage() {
  const companiesQuery = useQuery({
    queryKey: ["platform", "companies"],
    queryFn: () => apiRequest<CompanyResponse[]>("/platform/companies"),
  });

  const total = companiesQuery.data?.length ?? "…";
  const active = companiesQuery.data?.filter((c) => c.status === "active").length ?? "…";
  const suspended = companiesQuery.data?.filter((c) => c.status === "suspended") ?? [];

  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Cross-company overview" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <HeroStat
            label={suspended.length > 0 ? "Suspended companies" : "Active companies"}
            value={suspended.length > 0 ? suspended.length : active}
            tone={suspended.length > 0 ? "danger" : "success"}
            subtext={suspended.length > 0 ? "Need a decision — reactivate or leave suspended" : "All tenants currently operating"}
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:col-span-7">
          <StatCard label="Total companies" value={total} tone="neutral" />
          <StatCard label="Active" value={active} tone="success" />
        </div>
      </div>

      <DatabaseSecurityCard />

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-7">
          <LinkTile to="/platform/companies" icon="buildingOffice" label="Companies" description="Create, suspend, and reactivate tenant companies" />
        </div>
        <div className="lg:col-span-5">
          <Card>
            <SectionLabel>Needs attention</SectionLabel>
            {suspended.length === 0 ? (
              <EmptyState>No suspended companies right now.</EmptyState>
            ) : (
              <ul className="space-y-3">
                {suspended.map((c) => (
                  <li key={c.id} className="flex items-center justify-between gap-2 text-sm">
                    <span className="truncate text-slate-800 dark:text-slate-100">{c.name}</span>
                    <Badge tone="danger">suspended</Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
