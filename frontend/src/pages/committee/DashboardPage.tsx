import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { HeroStat, LinkTile, PageHeader, StatCard } from "../../components/ui";
import type { CommitteeQueueItemResponse } from "../../schemas/committee";
import type { CreditApplicationResponse } from "../../schemas/credit";

export function CommitteeDashboardPage() {
  const queueQuery = useQuery({
    queryKey: ["committee", "queue"],
    queryFn: () => apiRequest<CommitteeQueueItemResponse[]>("/committee/queue"),
  });
  const decisionsQuery = useQuery({
    queryKey: ["committee", "decisions", "me"],
    queryFn: () => apiRequest<CreditApplicationResponse[]>("/committee/decisions/me"),
  });

  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Applications escalated above a branch's delegated limit" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <HeroStat
            label="Pending committee review"
            value={queueQuery.data?.length ?? "…"}
            tone="brand"
            subtext="Escalated above the branch's own limit"
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:col-span-8">
          <StatCard label="Your decisions to date" value={decisionsQuery.data?.length ?? "…"} tone="neutral" />
          <StatCard
            label="In queue right now"
            value={queueQuery.data?.length ?? "…"}
            tone={queueQuery.data && queueQuery.data.length > 0 ? "brand" : "success"}
          />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <LinkTile to="/committee/queue" icon="documentText" label="Committee Queue" description="Decide escalated applications" />
        <LinkTile to="/committee/decisions" icon="checkCircle" label="My Decisions" description="Your own approval and rejection history" />
      </div>
    </AppShell>
  );
}
