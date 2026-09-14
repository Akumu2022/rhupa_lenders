import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { BarList, Badge, Card, EmptyState, HeroStat, LinkTile, PageHeader, SectionLabel, StatCard } from "../../components/ui";
import {
  describeApplicationLifecycle,
  type CollectionsQueueItemResponse,
  type CreditApplicationResponse,
} from "../../schemas/credit";

/** CLAUDE.md §8/§26 (M13): credit_officer prepares — decisions and
 * disbursement now belong to branch_manager/committee and
 * cashier_finance_officer respectively (src/pages/branch-manager/,
 * src/pages/finance/). "Your recent decisions" only ever shows
 * pre-M13 historical rows now, since this role no longer decides. */
export function CreditDashboardPage() {
  const queueQuery = useQuery({
    queryKey: ["credit", "queue"],
    queryFn: () => apiRequest<CreditApplicationResponse[]>("/credit/queue"),
  });
  const collectionsQuery = useQuery({
    queryKey: ["collections"],
    queryFn: () => apiRequest<CollectionsQueueItemResponse[]>("/credit/loans/collections"),
  });
  const decisionsQuery = useQuery({
    queryKey: ["credit", "decisions", "me"],
    queryFn: () => apiRequest<CreditApplicationResponse[]>("/credit/decisions/me"),
  });

  const recentDecisions = (decisionsQuery.data ?? []).slice(0, 5);

  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Prepare customers and applications for your branch manager to decide" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <HeroStat
            label="Awaiting a decision"
            value={queueQuery.data?.length ?? "…"}
            tone="brand"
            subtext="Applications you've prepared, still in review"
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:col-span-8">
          <StatCard
            label="Overdue (collections)"
            value={collectionsQuery.data?.length ?? "…"}
            tone={collectionsQuery.data && collectionsQuery.data.length > 0 ? "danger" : "success"}
          />
          <StatCard label="Your past decisions" value={decisionsQuery.data?.length ?? "…"} tone="neutral" />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <LinkTile to="/credit/applications" icon="documentText" label="Applications" description="What you've prepared, still in review" />
        <LinkTile to="/credit/collections" icon="archiveBox" label="Collections" description="Overdue loans awaiting follow-up" />
        <LinkTile to="/credit/decisions" icon="checkCircle" label="My Decisions" description="Your historical approval and rejection record" />
      </div>

      <Card className="mt-4">
        <SectionLabel>Today's workload</SectionLabel>
        <BarList
          items={[
            { label: "Awaiting a decision", value: queueQuery.data?.length ?? 0, tone: "warning" },
            { label: "Overdue collections", value: collectionsQuery.data?.length ?? 0, tone: "danger" },
          ]}
        />
      </Card>

      <Card className="mt-4">
        <SectionLabel>Recent history</SectionLabel>
        {recentDecisions.length === 0 ? (
          <EmptyState>No decisions on record.</EmptyState>
        ) : (
          <ul className="space-y-3">
            {recentDecisions.map((application) => {
              const { label, tone } = describeApplicationLifecycle(application);
              return (
                <li key={application.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate text-slate-800 dark:text-slate-100">{application.customer_full_name}</span>
                  <Badge tone={tone}>{label}</Badge>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </AppShell>
  );
}
