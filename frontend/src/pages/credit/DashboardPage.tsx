import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { BarList, Badge, Button, Card, EmptyState, HeroStat, LinkTile, PageHeader, SectionLabel, StatCard } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { useToast } from "../../components/toast";
import {
  describeApplicationLifecycle,
  type CollectionsQueueItemResponse,
  type CreditApplicationResponse,
  type DisbursementResponse,
  type PendingDisbursementResponse,
} from "../../schemas/credit";

function DisburseButton({ loan }: { loan: PendingDisbursementResponse }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const disburse = useMutation({
    mutationFn: () => apiRequest<DisbursementResponse>(`/credit/loans/${loan.id}/disburse`, { method: "POST" }),
    onSuccess: () => {
      // Disbursing changes this loan's status, which several other cached
      // views derive from (recent decisions' lifecycle badge, collections,
      // the system_administrator portfolio) — invalidate broadly so nothing keeps
      // showing "awaiting disbursement" after it's actually been disbursed.
      void queryClient.invalidateQueries({ queryKey: ["credit"] });
      void queryClient.invalidateQueries({ queryKey: ["admin", "portfolio"] });
      void queryClient.invalidateQueries({ queryKey: ["admin", "audit-log"] });
      toast(`Disbursed KES ${loan.principal} to ${loan.customer_full_name}.`, "success");
    },
    onError: (err) => toast(getErrorMessage(err), "error"),
  });

  return (
    <Button className="px-2 py-1 text-xs" disabled={disburse.isPending} onClick={() => disburse.mutate()}>
      {disburse.isPending ? "Disbursing…" : "Disburse"}
    </Button>
  );
}

export function CreditDashboardPage() {
  const queueQuery = useQuery({
    queryKey: ["credit", "queue"],
    queryFn: () => apiRequest<CreditApplicationResponse[]>("/credit/queue"),
  });
  const pendingDisbursementQuery = useQuery({
    queryKey: ["credit", "pending-disbursement"],
    queryFn: () => apiRequest<PendingDisbursementResponse[]>("/credit/loans/pending-disbursement"),
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
      <PageHeader title="Dashboard" subtitle="Approve applications and disburse approved loans" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <HeroStat label="Pending decisions" value={queueQuery.data?.length ?? "…"} tone="brand" subtext="Applications awaiting your review" />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:col-span-8">
          <StatCard label="Ready to disburse" value={pendingDisbursementQuery.data?.length ?? "…"} tone="success" />
          <StatCard
            label="Overdue (collections)"
            value={collectionsQuery.data?.length ?? "…"}
            tone={collectionsQuery.data && collectionsQuery.data.length > 0 ? "danger" : "success"}
          />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <LinkTile to="/credit/applications" icon="documentText" label="Applications" description="Approve or reject pending applications" />
        <LinkTile to="/credit/collections" icon="archiveBox" label="Collections" description="Overdue loans awaiting follow-up" />
        <LinkTile to="/credit/decisions" icon="checkCircle" label="My Decisions" description="Your own approval and rejection history" />
      </div>

      <Card className="mt-4">
        <SectionLabel>Today's workload</SectionLabel>
        <BarList
          items={[
            { label: "Pending review", value: queueQuery.data?.length ?? 0, tone: "warning" },
            { label: "Ready to disburse", value: pendingDisbursementQuery.data?.length ?? 0, tone: "success" },
            { label: "Overdue collections", value: collectionsQuery.data?.length ?? 0, tone: "danger" },
          ]}
        />
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <Card>
            <SectionLabel>Ready to disburse</SectionLabel>
            <DataTable
              columns={[
                { key: "customer", header: "Customer", accessor: (l: PendingDisbursementResponse) => l.customer_full_name },
                { key: "product", header: "Product", accessor: (l) => l.loan_product_name },
                {
                  key: "principal",
                  header: "Principal",
                  sortable: true,
                  accessor: (l) => Number(l.principal),
                  render: (l) => `KES ${l.principal}`,
                },
                {
                  key: "repayable",
                  header: "Total repayable",
                  accessor: (l) => Number(l.total_repayable),
                  render: (l) => `KES ${l.total_repayable}`,
                },
              ]}
              data={pendingDisbursementQuery.data}
              getRowId={(l) => l.id}
              isLoading={pendingDisbursementQuery.isLoading}
              isError={pendingDisbursementQuery.isError}
              emptyMessage="No approved loans waiting to be disbursed."
              rowActions={(l) => <DisburseButton loan={l} />}
            />
          </Card>
        </div>

        <div className="lg:col-span-4">
          <Card>
            <SectionLabel>Your recent decisions</SectionLabel>
            {recentDecisions.length === 0 ? (
              <EmptyState>No decisions yet.</EmptyState>
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
        </div>
      </div>
    </AppShell>
  );
}
