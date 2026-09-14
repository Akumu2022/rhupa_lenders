import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Banner, Button, Card, PageHeader, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import type { CreditApplicationResponse } from "../../schemas/credit";
import type { CommitteeQueueItemResponse } from "../../schemas/committee";

function DecisionDrawer({
  application,
  onClose,
}: {
  application: CommitteeQueueItemResponse | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [comments, setComments] = useState("");
  const [error, setError] = useState<string | null>(null);

  function invalidateAndClose(message: string) {
    void queryClient.invalidateQueries({ queryKey: ["committee"] });
    toast(message, "success");
    setComments("");
    onClose();
  }

  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      apiRequest<CreditApplicationResponse>(`/committee/applications/${application!.id}/decide`, {
        method: "POST",
        body: { decision, comments },
      }),
    onSuccess: (_result, decision) =>
      invalidateAndClose(
        decision === "approve"
          ? `Approved — loan created for ${application!.customer_full_name}.`
          : `${application!.customer_full_name}'s application was rejected.`,
      ),
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Drawer open={application !== null} onClose={onClose} title={application ? application.customer_full_name : ""}>
      {application ? (
        <div className="space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">{application.customer_email}</p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <div>
              <dt className="text-slate-500 dark:text-slate-400">Product</dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">{application.loan_product_name}</dd>
            </div>
            <div>
              <dt className="text-slate-500 dark:text-slate-400">Amount requested</dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">KES {application.amount_requested}</dd>
            </div>
          </dl>

          {/* CLAUDE.md §26: "everything the branch manager saw plus the
              branch manager's own decision/comments" — shown read-only. */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm dark:border-slate-800 dark:bg-slate-900/60">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
              Branch manager's recommendation — {application.branch_manager_name}
            </p>
            <p className="mt-1 text-slate-700 dark:text-slate-300">{application.branch_manager_comments}</p>
          </div>

          <div className="border-t border-slate-100 pt-4 dark:border-slate-800">
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400">
              Comments (required for either decision)
            </label>
            <TextInput
              className="mt-1"
              placeholder="e.g. Concur with branch manager's recommendation"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
            />
            <div className="mt-3 flex gap-2">
              <Button disabled={!comments.trim() || decide.isPending} onClick={() => decide.mutate("approve")}>
                Approve
              </Button>
              <Button
                variant="danger"
                disabled={!comments.trim() || decide.isPending}
                onClick={() => decide.mutate("reject")}
              >
                Reject
              </Button>
            </div>
          </div>
          {error ? <Banner kind="error">{error}</Banner> : null}
        </div>
      ) : null}
    </Drawer>
  );
}

export function CommitteeQueuePage() {
  const [selected, setSelected] = useState<CommitteeQueueItemResponse | null>(null);

  const queueQuery = useQuery({
    queryKey: ["committee", "queue"],
    queryFn: () => apiRequest<CommitteeQueueItemResponse[]>("/committee/queue"),
  });

  return (
    <AppShell>
      <PageHeader title="Committee queue" subtitle="Applications escalated above a branch's delegated limit" />

      <Card>
        <DataTable
          columns={[
            { key: "customer", header: "Customer", sortable: true, accessor: (a: CommitteeQueueItemResponse) => a.customer_full_name },
            { key: "product", header: "Product", accessor: (a) => a.loan_product_name },
            {
              key: "amount",
              header: "Amount",
              sortable: true,
              accessor: (a) => Number(a.amount_requested),
              render: (a) => `KES ${a.amount_requested}`,
            },
            { key: "manager", header: "Branch manager", accessor: (a) => a.branch_manager_name },
            {
              key: "created_at",
              header: "Submitted",
              sortable: true,
              accessor: (a) => a.created_at,
              render: (a) => new Date(a.created_at).toLocaleString(),
            },
          ]}
          data={queueQuery.data}
          getRowId={(a) => a.id}
          isLoading={queueQuery.isLoading}
          isError={queueQuery.isError}
          searchKeys={["customer"]}
          searchPlaceholder="Search by customer…"
          emptyMessage="Nothing escalated to the committee right now."
          onRowClick={(a) => setSelected(a)}
          rowActions={() => <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">Review →</span>}
        />
      </Card>

      <DecisionDrawer application={selected} onClose={() => setSelected(null)} />
    </AppShell>
  );
}
