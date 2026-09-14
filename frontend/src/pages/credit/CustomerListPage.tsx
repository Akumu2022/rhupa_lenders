import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Button, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { kycStatusTone } from "../../schemas/compliance";
import type { CustomerResponse } from "../../schemas/customers";

export function CustomerListPage() {
  const navigate = useNavigate();

  const customersQuery = useQuery({
    queryKey: ["customers"],
    queryFn: () => apiRequest<CustomerResponse[]>("/customers"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Customers"
        subtitle="Registered customers in your branch"
        actions={<Button onClick={() => navigate("/credit/customers/new")}>New Customer</Button>}
      />

      <Card>
        <DataTable
          columns={[
            {
              key: "customer_number",
              header: "Customer #",
              accessor: (c: CustomerResponse) => c.customer_number ?? "—",
              render: (c) => <span className="font-mono text-xs">{c.customer_number ?? "—"}</span>,
            },
            { key: "name", header: "Name", sortable: true, accessor: (c) => c.full_name },
            { key: "email", header: "Email", accessor: (c) => c.email },
            {
              key: "kyc_status",
              header: "KYC Status",
              accessor: (c) => c.kyc_status,
              render: (c) => <Badge tone={kycStatusTone(c.kyc_status)}>{c.kyc_status}</Badge>,
            },
            {
              key: "created_at",
              header: "Registered",
              sortable: true,
              accessor: (c) => c.created_at,
              render: (c) => new Date(c.created_at).toLocaleDateString(),
            },
          ]}
          data={customersQuery.data}
          getRowId={(c) => c.id}
          isLoading={customersQuery.isLoading}
          isError={customersQuery.isError}
          searchKeys={["name", "email", "customer_number"]}
          searchPlaceholder="Search by name, email, or customer #…"
          emptyMessage="No customers registered yet."
          onRowClick={(c) => navigate(`/credit/customers/${c.id}`)}
        />
      </Card>
    </AppShell>
  );
}
