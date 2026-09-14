import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import type { CollectionsQueueItemResponse } from "../../schemas/credit";

export function BranchManagerCollectionsPage() {
  const collectionsQuery = useQuery({
    queryKey: ["branch-manager", "collections"],
    queryFn: () => apiRequest<CollectionsQueueItemResponse[]>("/branch-manager/collections"),
  });

  return (
    <AppShell>
      <PageHeader title="Collections" subtitle="Overdue loans in your branch" />

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
          emptyMessage="No loans in your branch are currently overdue."
        />
      </Card>
    </AppShell>
  );
}
