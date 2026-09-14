import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Card, EmptyState, HeroStat, LinkTile, PageHeader, SectionLabel, StatCard } from "../../components/ui";
import type { CompanyResponse } from "../../schemas/company";

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
