import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { BarList, Card, HeroStat, LinkTile, PageHeader, SectionLabel, StatCard } from "../../components/ui";
import type { PortfolioSummaryResponse } from "../../schemas/admin";
import type { BranchRankingItemResponse } from "../../schemas/management";

/** CLAUDE.md §9/§30: management — organization-wide, aggregates only, no
 * individual customer PII on this screen. */
export function ManagementDashboardPage() {
  const portfolioQuery = useQuery({
    queryKey: ["management", "portfolio"],
    queryFn: () => apiRequest<PortfolioSummaryResponse>("/management/portfolio"),
  });
  const rankingQuery = useQuery({
    queryKey: ["management", "branch-ranking"],
    queryFn: () => apiRequest<BranchRankingItemResponse[]>("/management/branch-ranking"),
  });

  const topBranches = (rankingQuery.data ?? []).slice(0, 5);

  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Organization-wide reporting" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <HeroStat
            label="Portfolio at risk"
            value={portfolioQuery.data ? `${portfolioQuery.data.par_percentage}%` : "…"}
            tone={portfolioQuery.data && Number(portfolioQuery.data.par_percentage) > 0 ? "danger" : "success"}
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:col-span-8">
          <StatCard label="Total disbursed" value={portfolioQuery.data ? `KES ${portfolioQuery.data.total_disbursed}` : "…"} tone="brand" />
          <StatCard label="Active borrowers" value={portfolioQuery.data?.active_borrowers ?? "…"} tone="neutral" />
          <StatCard label="Active loans" value={portfolioQuery.data?.active_loans ?? "…"} tone="neutral" />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <LinkTile to="/management/reports" icon="archiveBox" label="Reports" description="Date-range summary reports" />
        <LinkTile to="/management/branch-ranking" icon="chartBar" label="Branch Ranking" description="Branches ranked by disbursed" />
        <LinkTile to="/management/staff-performance" icon="users" label="Staff Performance" description="Decisions by branch managers and committee" />
      </div>

      <Card className="mt-4">
        <SectionLabel>Top branches by disbursed volume</SectionLabel>
        {topBranches.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">No active branches yet.</p>
        ) : (
          <BarList
            items={topBranches.map((b) => ({
              label: b.branch_name,
              value: Number(b.total_disbursed),
              tone: "brand" as const,
            }))}
            formatValue={(v) => `KES ${v.toLocaleString()}`}
          />
        )}
      </Card>
    </AppShell>
  );
}
