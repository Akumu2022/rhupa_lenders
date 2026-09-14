import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { ROLE_LABELS } from "../../components/nav";
import type { UserResponse } from "../../schemas/staff";

/** CLAUDE.md §9: "view officer portfolios" — read-only, unlike
 * system_administrator's Users page (no create/deactivate here). */
export function BranchManagerStaffPage() {
  const staffQuery = useQuery({
    queryKey: ["branch-manager", "staff"],
    queryFn: () => apiRequest<UserResponse[]>("/branch-manager/staff"),
  });

  return (
    <AppShell>
      <PageHeader title="Staff" subtitle="Everyone assigned to your branch" />

      <Card>
        <DataTable
          columns={[
            { key: "name", header: "Name", sortable: true, accessor: (s: UserResponse) => s.full_name },
            { key: "email", header: "Email", accessor: (s) => s.email },
            {
              key: "role",
              header: "Role",
              accessor: (s) => s.role,
              render: (s) => <Badge tone="brand">{ROLE_LABELS[s.role] ?? s.role.replace(/_/g, " ")}</Badge>,
            },
            {
              key: "status",
              header: "Status",
              accessor: (s) => (s.is_active ? "active" : "inactive"),
              render: (s) => <Badge tone={s.is_active ? "success" : "neutral"}>{s.is_active ? "Active" : "Inactive"}</Badge>,
            },
          ]}
          data={staffQuery.data}
          getRowId={(s) => s.id}
          isLoading={staffQuery.isLoading}
          isError={staffQuery.isError}
          searchKeys={["name", "email"]}
          searchPlaceholder="Search staff…"
          emptyMessage="No staff assigned to your branch yet."
        />
      </Card>
    </AppShell>
  );
}
