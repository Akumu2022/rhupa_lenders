import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Button, Card, PageHeader, Select } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { useToast } from "../../components/toast";
import { useAuth } from "../../auth/AuthContext";
import { kycStatusTone } from "../../schemas/compliance";
import type { CustomerResponse } from "../../schemas/customers";
import type { UserResponse } from "../../schemas/staff";

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

// Who may hand a customer to a different credit officer (backend:
// PATCH /customers/{id}/officer), and where each gets its officer list.
const OFFICER_SOURCE: Record<string, string> = {
  branch_manager: "/branch-manager/staff",
  system_administrator: "/staff",
};

export function CustomerListPage() {
  const navigate = useNavigate();
  const { auth } = useAuth();
  const role = auth?.role ?? "";
  const basePath = CUSTOMERS_BASE_PATH[role] ?? "/credit/customers";
  const canRegister = role === "credit_officer";
  const officerSource = OFFICER_SOURCE[role];
  const [params, setParams] = useSearchParams();
  const mine = canRegister && params.get("mine") === "1";

  const customersQuery = useQuery({
    queryKey: ["customers", mine],
    queryFn: () => apiRequest<CustomerResponse[]>(`/customers${mine ? "?mine=true" : ""}`),
  });
  const officersQuery = useQuery({
    queryKey: ["officers", officerSource],
    queryFn: () => apiRequest<UserResponse[]>(officerSource!),
    enabled: Boolean(officerSource),
    select: (users) => users.filter((u) => u.role === "credit_officer" && u.is_active),
  });

  function toggleMine() {
    const p = new URLSearchParams(params);
    if (mine) p.delete("mine");
    else p.set("mine", "1");
    setParams(p, { replace: true });
  }

  return (
    <AppShell>
      <PageHeader
        title="Customers"
        subtitle={canRegister ? "Registered customers in your branch" : "Registered customers"}
        actions={
          canRegister ? (
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
                <input type="checkbox" checked={mine} onChange={toggleMine} className="rounded" />
                My customers only
              </label>
              <Button onClick={() => navigate("/credit/customers/new")}>New Customer</Button>
            </div>
          ) : undefined
        }
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
              key: "officer",
              header: "Officer",
              sortable: true,
              accessor: (c) => c.assigned_officer_name ?? "",
              render: (c) =>
                officerSource ? (
                  <OfficerPicker customer={c} officers={officersQuery.data ?? []} />
                ) : (
                  (c.assigned_officer_name ?? <span className="text-slate-400">Unassigned</span>)
                ),
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
          searchKeys={["name", "email", "customer_number", "officer"]}
          searchPlaceholder="Search by name, email, customer # or officer…"
          emptyMessage={mine ? "No customers are assigned to you yet." : "No customers registered yet."}
          onRowClick={(c) => navigate(`${basePath}/${c.id}`)}
        />
      </Card>
    </AppShell>
  );
}

/** Reassign a customer to an active credit officer in the customer's own
 * branch; the server enforces the same rule and audits the change. */
function OfficerPicker({ customer, officers }: { customer: CustomerResponse; officers: UserResponse[] }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [saving, setSaving] = useState(false);
  const eligible = officers.filter((o) => o.branch_id === customer.branch_id);

  async function change(value: string) {
    setSaving(true);
    try {
      const updated = await apiRequest<CustomerResponse>(`/customers/${customer.id}/officer`, {
        method: "PATCH",
        body: { officer_id: value ? Number(value) : null },
      });
      toast(
        updated.assigned_officer_name
          ? `${customer.full_name} assigned to ${updated.assigned_officer_name}.`
          : `${customer.full_name} is now unassigned.`,
        "success",
      );
      void queryClient.invalidateQueries({ queryKey: ["customers"] });
      void queryClient.invalidateQueries({ queryKey: ["analytics"] });
    } catch (err) {
      toast(getErrorMessage(err), "error");
    } finally {
      setSaving(false);
    }
  }

  if (customer.branch_id === null) return <span className="text-xs text-slate-400">No branch yet</span>;
  return (
    // Stop the row's click-through to the customer page while choosing.
    <div onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      <Select
        aria-label={`Officer for ${customer.full_name}`}
        value={customer.assigned_officer_id ?? ""}
        disabled={saving}
        onChange={(e) => void change(e.target.value)}
        className="w-44 py-1 text-xs"
      >
        <option value="">Unassigned</option>
        {eligible.map((o) => (
          <option key={o.id} value={o.id}>
            {o.full_name}
          </option>
        ))}
      </Select>
    </div>
  );
}
