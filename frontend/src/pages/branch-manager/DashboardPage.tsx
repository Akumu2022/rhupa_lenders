import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { BarList, Card, HeroStat, LinkTile, PageHeader, SectionLabel, StatCard } from "../../components/ui";
import type { BranchQueueItemResponse } from "../../schemas/branchManager";
import type { CollectionsQueueItemResponse } from "../../schemas/credit";
import type { PortfolioSummaryResponse } from "../../schemas/admin";

/** CLAUDE.md §9/§26: branch manager's command dashboard — the client PRD's
 * full daily-target layout ships once collections carries richer targets
 * (§29); this is the real, working slice built on what M13/M15-lite ship
 * today (§18: not built = not faked, but nothing here is faked either). */
export function BranchManagerDashboardPage() {
  const queueQuery = useQuery({
    queryKey: ["branch-manager", "queue"],
    queryFn: () => apiRequest<BranchQueueItemResponse[]>("/branch-manager/queue"),
  });
  const portfolioQuery = useQuery({
    queryKey: ["branch-manager", "portfolio"],
    queryFn: () => apiRequest<PortfolioSummaryResponse>("/branch-manager/portfolio"),
  });
  const collectionsQuery = useQuery({
    queryKey: ["branch-manager", "collections"],
    queryFn: () => apiRequest<CollectionsQueueItemResponse[]>("/branch-manager/collections"),
  });

  const overLimitCount = queueQuery.data?.filter((a) => a.over_limit).length ?? 0;

  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Your branch at a glance" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <HeroStat
            label="Awaiting your decision"
            value={queueQuery.data?.length ?? "…"}
            tone="brand"
            subtext={overLimitCount > 0 ? `${overLimitCount} above your delegated limit` : "All within your delegated limit"}
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:col-span-8">
          <StatCard
            label="Portfolio at risk"
            value={portfolioQuery.data ? `${portfolioQuery.data.par_percentage}%` : "…"}
            tone={portfolioQuery.data && Number(portfolioQuery.data.par_percentage) > 0 ? "danger" : "success"}
          />
          <StatCard
            label="Overdue loans"
            value={collectionsQuery.data?.length ?? "…"}
            tone={collectionsQuery.data && collectionsQuery.data.length > 0 ? "danger" : "success"}
          />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
        <LinkTile to="/branch-manager/applications" icon="documentText" label="Applications" description="Decide escalated applications" />
        <LinkTile to="/branch-manager/staff" icon="users" label="Staff" description="Everyone in your branch" />
        <LinkTile to="/branch-manager/portfolio" icon="chartBar" label="Portfolio" description="Your branch's aggregate figures" />
        <LinkTile to="/branch-manager/collections" icon="archiveBox" label="Collections" description="Overdue loans in your branch" />
      </div>

      <Card className="mt-4">
        <SectionLabel>Branch snapshot</SectionLabel>
        <BarList
          items={[
            { label: "Active loans", value: portfolioQuery.data?.active_loans ?? 0, tone: "brand" },
            { label: "Overdue", value: portfolioQuery.data?.overdue_loans ?? 0, tone: "warning" },
            { label: "Defaulted", value: portfolioQuery.data?.defaulted_loans ?? 0, tone: "danger" },
          ]}
        />
      </Card>
    </AppShell>
  );
}
