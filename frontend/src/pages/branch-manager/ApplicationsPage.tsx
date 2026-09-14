import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, PageHeader, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import type { CreditApplicationResponse } from "../../schemas/credit";
import type { BranchQueueItemResponse } from "../../schemas/branchManager";

function DecisionDrawer({
  application,
  onClose,
}: {
  application: BranchQueueItemResponse | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [comments, setComments] = useState("");
  const [error, setError] = useState<string | null>(null);

  function invalidateAndClose(message: string) {
    void queryClient.invalidateQueries({ queryKey: ["branch-manager"] });
    toast(message, "success");
    setComments("");
    onClose();
  }

  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject" | "escalate") =>
      apiRequest<CreditApplicationResponse>(`/branch-manager/applications/${application!.id}/decide`, {
        method: "POST",
        body: { decision, comments },
      }),
    onSuccess: (result, decision) => {
      const messages: Record<string, string> = {
        approve: `Approved — loan created for ${application!.customer_full_name}.`,
        reject: `${application!.customer_full_name}'s application was rejected.`,
        escalate: `Escalated ${application!.customer_full_name}'s application to the committee.`,
      };
      invalidateAndClose(messages[decision] ?? `Application ${result.status}.`);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const overLimit = application?.over_limit ?? false;

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
            <div>
              <dt className="text-slate-500 dark:text-slate-400">Your delegated limit</dt>
              <dd className="font-medium text-slate-900 dark:text-slate-100">KES {application.effective_limit}</dd>
            </div>
          </dl>

          {overLimit ? (
            <Banner kind="info">
              This amount is above your delegated limit — you can only escalate it to the loan vetting committee.
            </Banner>
          ) : null}

          <div className="border-t border-slate-100 pt-4 dark:border-slate-800">
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400">
              Comments (required for any decision)
            </label>
            <TextInput
              className="mt-1"
              placeholder={overLimit ? "e.g. Strong application, recommending approval" : "e.g. Good repayment history on prior loans"}
              value={comments}
              onChange={(e) => setComments(e.target.value)}
            />
            <div className="mt-3 flex gap-2">
              {overLimit ? (
                <Button disabled={!comments.trim() || decide.isPending} onClick={() => decide.mutate("escalate")}>
                  Escalate to committee
                </Button>
              ) : (
                <>
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
                </>
              )}
            </div>
          </div>
          {error ? <Banner kind="error">{error}</Banner> : null}
        </div>
      ) : null}
    </Drawer>
  );
}

export function BranchManagerApplicationsPage() {
  const [selected, setSelected] = useState<BranchQueueItemResponse | null>(null);

  const queueQuery = useQuery({
    queryKey: ["branch-manager", "queue"],
    queryFn: () => apiRequest<BranchQueueItemResponse[]>("/branch-manager/queue"),
  });

  return (
    <AppShell>
      <PageHeader title="Applications" subtitle="Decide applications escalated from your branch's credit officers" />

      <Card>
        <DataTable
          columns={[
            { key: "customer", header: "Customer", sortable: true, accessor: (a: BranchQueueItemResponse) => a.customer_full_name },
            { key: "email", header: "Email", accessor: (a) => a.customer_email },
            { key: "product", header: "Product", accessor: (a) => a.loan_product_name },
            {
              key: "amount",
              header: "Amount",
              sortable: true,
              accessor: (a) => Number(a.amount_requested),
              render: (a) => `KES ${a.amount_requested}`,
            },
            {
              key: "limit",
              header: "Within limit?",
              accessor: (a) => (a.over_limit ? "over" : "within"),
              render: (a) => (
                <Badge tone={a.over_limit ? "warning" : "success"}>{a.over_limit ? "Over limit" : "Within limit"}</Badge>
              ),
            },
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
          searchKeys={["customer", "email"]}
          searchPlaceholder="Search by customer or email…"
          emptyMessage="No applications waiting for a branch decision."
          onRowClick={(a) => setSelected(a)}
          rowActions={() => <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">Review →</span>}
        />
      </Card>

      <DecisionDrawer application={selected} onClose={() => setSelected(null)} />
    </AppShell>
  );
}
