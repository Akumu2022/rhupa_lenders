import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { describeApplicationLifecycle, type CreditApplicationResponse } from "../../schemas/credit";

export function CommitteeDecisionsPage() {
  const decisionsQuery = useQuery({
    queryKey: ["committee", "decisions", "me"],
    queryFn: () => apiRequest<CreditApplicationResponse[]>("/committee/decisions/me"),
  });

  return (
    <AppShell>
      <PageHeader title="My decisions" subtitle="Applications you've personally approved or rejected" />

      <Card>
        <DataTable
          columns={[
            { key: "customer", header: "Customer", sortable: true, accessor: (a: CreditApplicationResponse) => a.customer_full_name },
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
            { key: "notes", header: "Notes", accessor: (a) => a.review_notes ?? "" },
            {
              key: "reviewed_at",
              header: "Decided",
              sortable: true,
              accessor: (a) => a.reviewed_at ?? "",
              render: (a) => (a.reviewed_at ? new Date(a.reviewed_at).toLocaleString() : "—"),
            },
          ]}
          data={decisionsQuery.data}
          getRowId={(a) => a.id}
          isLoading={decisionsQuery.isLoading}
          isError={decisionsQuery.isError}
          emptyMessage="You haven't made any decisions yet."
        />
      </Card>
    </AppShell>
  );
}
