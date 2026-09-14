import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import type { AdminLoanResponse } from "../../schemas/admin";

// Same mapping as pages/customer/shared.tsx::loanStatusTone — §18: one status
// badge color vocabulary everywhere, staff and customer views alike.
function statusTone(status: AdminLoanResponse["status"]): "success" | "info" | "warning" | "danger" {
  if (status === "repaid") return "success";
  if (status === "active") return "info";
  if (status === "overdue") return "warning";
  if (status === "defaulted") return "danger";
  return "warning";
}

export function CompanyLoansPage() {
  const loansQuery = useQuery({
    queryKey: ["admin", "loans"],
    queryFn: () => apiRequest<AdminLoanResponse[]>("/admin/loans"),
  });

  return (
    <AppShell>
      <PageHeader title="Loans" subtitle="Every loan in your company, past and present" />

      <Card>
        <DataTable
          columns={[
            { key: "customer", header: "Customer", sortable: true, accessor: (l: AdminLoanResponse) => l.customer_full_name },
            { key: "product", header: "Product", accessor: (l) => l.loan_product_name },
            {
              key: "principal",
              header: "Principal",
              sortable: true,
              accessor: (l) => Number(l.principal),
              render: (l) => `KES ${l.principal}`,
            },
            {
              key: "outstanding",
              header: "Outstanding",
              sortable: true,
              accessor: (l) => Number(l.outstanding_balance),
              render: (l) => `KES ${l.outstanding_balance}`,
            },
            {
              key: "status",
              header: "Status",
              accessor: (l) => l.status,
              render: (l) => <Badge tone={statusTone(l.status)}>{l.status}</Badge>,
            },
            {
              key: "created_at",
              header: "Opened",
              sortable: true,
              accessor: (l) => l.created_at,
              render: (l) => new Date(l.created_at).toLocaleDateString(),
            },
          ]}
          data={loansQuery.data}
          getRowId={(l) => l.id}
          isLoading={loansQuery.isLoading}
          isError={loansQuery.isError}
          searchKeys={["customer"]}
          searchPlaceholder="Search by customer…"
          emptyMessage="No loans yet."
        />
      </Card>
    </AppShell>
  );
}
