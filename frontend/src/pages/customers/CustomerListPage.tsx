import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Button, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { useAuth } from "../../auth/AuthContext";
import { kycStatusTone } from "../../schemas/compliance";
import type { CustomerResponse } from "../../schemas/customers";

// Shared by credit_officer, branch_manager, and system_administrator (all
// three are already allowed to read GET /customers and GET /customers/{id}
// on the backend — this page/route was the only missing piece for the
// latter two). Each role sees the same table; only the detail link's base
// path and the "New Customer" action differ by role.
const CUSTOMERS_BASE_PATH: Record<string, string> = {
  credit_officer: "/credit/customers",
  branch_manager: "/branch-manager/customers",
  system_administrator: "/admin/customers",
};

export function CustomerListPage() {
  const navigate = useNavigate();
  const { auth } = useAuth();
  const basePath = CUSTOMERS_BASE_PATH[auth?.role ?? ""] ?? "/credit/customers";
  const canRegister = auth?.role === "credit_officer";

  const customersQuery = useQuery({
    queryKey: ["customers"],
    queryFn: () => apiRequest<CustomerResponse[]>("/customers"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Customers"
        subtitle={canRegister ? "Registered customers in your branch" : "Registered customers"}
        actions={canRegister ? <Button onClick={() => navigate("/credit/customers/new")}>New Customer</Button> : undefined}
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
          onRowClick={(c) => navigate(`${basePath}/${c.id}`)}
        />
      </Card>
    </AppShell>
  );
}
