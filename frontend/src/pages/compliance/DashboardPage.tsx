import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Card, EmptyState, HeroStat, LinkTile, PageHeader, SectionLabel, StatCard } from "../../components/ui";
import type { ComplianceProfileResponse } from "../../schemas/compliance";

export function ComplianceDashboardPage() {
  const historyQuery = useQuery({
    queryKey: ["compliance", "history"],
    queryFn: () => apiRequest<ComplianceProfileResponse[]>("/compliance/history"),
  });

  const counts = historyQuery.data?.reduce(
    (acc, p) => ({ ...acc, [p.kyc_status]: acc[p.kyc_status] + 1 }),
    { pending: 0, verified: 0, rejected: 0 },
  );

  const recentDecisions = (historyQuery.data ?? [])
    .filter((p) => p.kyc_status !== "pending" && p.reviewed_at)
    .sort((a, b) => new Date(b.reviewed_at!).getTime() - new Date(a.reviewed_at!).getTime())
    .slice(0, 5);

  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Verify identity before a customer can apply for a loan" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <HeroStat label="Pending review" value={counts?.pending ?? "…"} tone="brand" subtext="Waiting in your queue right now" />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:col-span-8">
          <StatCard label="Verified" value={counts?.verified ?? "…"} tone="success" />
          <StatCard label="Rejected" value={counts?.rejected ?? "…"} tone="danger" />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-7">
          <LinkTile to="/compliance/queue" icon="clipboardList" label="KYC Queue" description="Review pending identity submissions" />
          <Card>
            <Banner kind="info">
              Verifying a customer's identity automatically unlocks their ability to apply — there's no separate button
              to "send" them to the credit officer. Once they submit an application, it automatically appears in the
              credit officer's queue.
            </Banner>
          </Card>
        </div>

        <div className="lg:col-span-5">
          <Card>
            <SectionLabel>Recently decided</SectionLabel>
            {recentDecisions.length === 0 ? (
              <EmptyState>No decisions yet.</EmptyState>
            ) : (
              <ul className="space-y-3">
                {recentDecisions.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-2 text-sm">
                    <span className="truncate text-slate-800 dark:text-slate-100">{p.customer_full_name}</span>
                    <Badge tone={p.kyc_status === "verified" ? "success" : "danger"}>{p.kyc_status}</Badge>
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
