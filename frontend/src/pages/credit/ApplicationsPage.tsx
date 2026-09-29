import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { GuarantorsCollateralPanel } from "../../components/GuarantorsCollateralPanel";
import { describeApplicationLifecycle, type CreditApplicationResponse } from "../../schemas/credit";

/** CLAUDE.md §8/§26 (M13): credit_officer prepares applications but no
 * longer decides them — this is now a read-only "what's still in review"
 * view of the officer's own branch, not an actionable queue. Deciding
 * happens at src/pages/branch-manager/ApplicationsPage.tsx (or the
 * committee's, once escalated). Preparation still includes attaching
 * guarantors/collateral (CLAUDE.md §27, M12) — the one editable action left
 * on this page, via the row drawer below. */
export function CreditApplicationsPage() {
  const [selected, setSelected] = useState<CreditApplicationResponse | null>(null);

  const queueQuery = useQuery({
    queryKey: ["credit", "queue"],
    queryFn: () => apiRequest<CreditApplicationResponse[]>("/credit/queue"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Applications"
        subtitle="Applications you've prepared, still awaiting a branch manager's or committee's decision"
      />

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
              key: "status",
              header: "Status",
              accessor: (a) => a.status,
              render: (a) => {
                const { label, tone } = describeApplicationLifecycle(a);
                return <Badge tone={tone}>{label}</Badge>;
              },
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
          emptyMessage="Nothing awaiting review right now."
          onRowClick={(a) => setSelected(a)}
          rowActions={() => <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">Guarantors →</span>}
        />
      </Card>

      <Drawer open={selected !== null} onClose={() => setSelected(null)} title={selected ? selected.customer_full_name : ""}>
        {selected ? <GuarantorsCollateralPanel applicationId={selected.id} editable /> : null}
      </Drawer>
    </AppShell>
  );
}
