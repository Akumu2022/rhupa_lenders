import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Banner, Button, Card, PageHeader, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { useToast } from "../../components/toast";
import type { CreditApplicationResponse, LoanApprovalResponse } from "../../schemas/credit";

function DecisionDrawer({
  application,
  onClose,
}: {
  application: CreditApplicationResponse | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  function invalidateAndClose(message: string) {
    // A decision moves the application off the queue and, once approved,
    // onto "ready to disburse" and "recent decisions" — invalidate broadly
    // so every one of those cached views picks up the change together.
    void queryClient.invalidateQueries({ queryKey: ["credit"] });
    toast(message, "success");
    setNotes("");
    onClose();
  }

  const approve = useMutation({
    mutationFn: () =>
      apiRequest<LoanApprovalResponse>(`/credit/applications/${application!.id}/approve`, {
        method: "POST",
        body: { notes },
      }),
    onSuccess: (result) =>
      invalidateAndClose(
        `Approved — KES ${result.loan.total_repayable} repayable by ${result.repayment_due_date}.`,
      ),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const reject = useMutation({
    mutationFn: () => apiRequest(`/credit/applications/${application!.id}/reject`, { method: "POST", body: { notes } }),
    onSuccess: () => invalidateAndClose(`${application!.customer_full_name}'s application was rejected.`),
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

          <div className="border-t border-slate-100 pt-4 dark:border-slate-800">
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400">
              Notes (required for either decision)
            </label>
            <TextInput
              className="mt-1"
              placeholder="e.g. Good repayment history on prior loans"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
            <div className="mt-3 flex gap-2">
              <Button disabled={!notes.trim() || approve.isPending} onClick={() => approve.mutate()}>
                Approve
              </Button>
              <Button variant="danger" disabled={!notes.trim() || reject.isPending} onClick={() => reject.mutate()}>
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

export function CreditApplicationsPage() {
  const [selected, setSelected] = useState<CreditApplicationResponse | null>(null);

  const queueQuery = useQuery({
    queryKey: ["credit", "queue"],
    queryFn: () => apiRequest<CreditApplicationResponse[]>("/credit/queue"),
  });

  return (
    <AppShell>
      <PageHeader title="Applications" subtitle="Approve or reject applications from KYC-verified customers" />

      <Card>
        <DataTable
          columns={[
            { key: "customer", header: "Customer", sortable: true, accessor: (a: CreditApplicationResponse) => a.customer_full_name },
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
          emptyMessage="No applications waiting for a decision."
          onRowClick={(a) => setSelected(a)}
          rowActions={() => <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">Review →</span>}
        />
      </Card>

      <DecisionDrawer application={selected} onClose={() => setSelected(null)} />
    </AppShell>
  );
}
