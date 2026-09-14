import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Button, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { useToast } from "../../components/toast";
import type { DisbursementResponse, PendingDisbursementResponse } from "../../schemas/credit";

function DisburseButton({ loan }: { loan: PendingDisbursementResponse }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const disburse = useMutation({
    mutationFn: () => apiRequest<DisbursementResponse>(`/finance/loans/${loan.id}/disburse`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance"] });
      void queryClient.invalidateQueries({ queryKey: ["admin", "portfolio"] });
      void queryClient.invalidateQueries({ queryKey: ["management"] });
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

/** CLAUDE.md §28 (M14): disbursement moved here from credit_officer — the
 * one concrete permission change the doc calls for. Still fully simulated
 * (§1), but still writes a ledger + audit row. */
export function FinanceDisbursementsPage() {
  const pendingQuery = useQuery({
    queryKey: ["finance", "disbursements"],
    queryFn: () => apiRequest<PendingDisbursementResponse[]>("/finance/disbursements"),
  });

  return (
    <AppShell>
      <PageHeader title="Disbursements" subtitle="Approved loans ready to disburse" />

      <Card>
        <DataTable
          columns={[
            { key: "customer", header: "Customer", accessor: (l: PendingDisbursementResponse) => l.customer_full_name },
            { key: "email", header: "Email", accessor: (l) => l.customer_email },
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
            {
              key: "created_at",
              header: "Approved",
              sortable: true,
              accessor: (l) => l.created_at,
              render: (l) => new Date(l.created_at).toLocaleString(),
            },
          ]}
          data={pendingQuery.data}
          getRowId={(l) => l.id}
          isLoading={pendingQuery.isLoading}
          isError={pendingQuery.isError}
          searchKeys={["customer", "email"]}
          searchPlaceholder="Search by customer…"
          emptyMessage="No approved loans waiting to be disbursed."
          rowActions={(l) => <DisburseButton loan={l} />}
        />
      </Card>
    </AppShell>
  );
}
