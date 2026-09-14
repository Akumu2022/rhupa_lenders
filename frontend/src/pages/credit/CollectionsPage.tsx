import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Button, Card, PageHeader, TextInput } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { useToast } from "../../components/toast";
import type { CollectionsQueueItemResponse, LoanResponse } from "../../schemas/credit";

function MarkDefaultedAction({ loan }: { loan: CollectionsQueueItemResponse }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const markDefaulted = useMutation({
    mutationFn: () =>
      apiRequest<LoanResponse>(`/credit/loans/${loan.id}/mark-defaulted`, {
        method: "POST",
        body: { reason },
      }),
    onSuccess: () => {
      setReason("");
      setOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["collections"] });
      toast(`${loan.customer_full_name}'s loan marked defaulted.`, "success");
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (!open) {
    return (
      <Button variant="danger" className="px-2 py-1 text-xs" onClick={() => setOpen(true)}>
        Mark defaulted
      </Button>
    );
  }

  return (
    <div className="flex items-center justify-end gap-2">
      <TextInput
        placeholder="Reason (required)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="w-44 py-1 text-xs"
      />
      <Button
        variant="danger"
        className="px-2 py-1 text-xs"
        disabled={!reason.trim() || markDefaulted.isPending}
        onClick={() => markDefaulted.mutate()}
      >
        Confirm
      </Button>
      {error ? <span className="text-xs text-rose-600 dark:text-rose-400">{error}</span> : null}
    </div>
  );
}

export function CollectionsPage() {
  const collectionsQuery = useQuery({
    queryKey: ["collections"],
    queryFn: () => apiRequest<CollectionsQueueItemResponse[]>("/credit/loans/collections"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Collections"
        subtitle="Loans past their repayment due date — a human decides if and when to mark one defaulted"
      />

      <Card>
        {collectionsQuery.isError ? <Banner kind="error">Could not load the collections queue</Banner> : null}
        <DataTable
          columns={[
            {
              key: "customer",
              header: "Customer",
              sortable: true,
              accessor: (l: CollectionsQueueItemResponse) => l.customer_full_name,
            },
            { key: "product", header: "Product", accessor: (l) => l.loan_product_name },
            {
              key: "outstanding",
              header: "Outstanding",
              sortable: true,
              accessor: (l) => Number(l.outstanding_balance),
              render: (l) => `KES ${l.outstanding_balance}`,
            },
            {
              key: "days_overdue",
              header: "Days overdue",
              sortable: true,
              accessor: (l) => l.days_overdue,
              render: (l) => <Badge tone="danger">{l.days_overdue}d overdue</Badge>,
            },
            {
              key: "due_date",
              header: "Was due",
              accessor: (l) => l.earliest_overdue_due_date,
              render: (l) => new Date(l.earliest_overdue_due_date).toLocaleDateString(),
            },
          ]}
          data={collectionsQuery.data}
          getRowId={(l) => l.id}
          isLoading={collectionsQuery.isLoading}
          searchKeys={["customer"]}
          searchPlaceholder="Search by customer…"
          emptyMessage="No loans are currently overdue."
          rowActions={(l) => <MarkDefaultedAction loan={l} />}
        />
      </Card>
    </AppShell>
  );
}
