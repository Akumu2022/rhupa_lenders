import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import { ROLE_LABELS } from "../../components/nav";
import type { StaffPerformanceItemResponse } from "../../schemas/management";

export function ManagementStaffPerformancePage() {
  const performanceQuery = useQuery({
    queryKey: ["management", "staff-performance"],
    queryFn: () => apiRequest<StaffPerformanceItemResponse[]>("/management/staff-performance"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Staff performance"
        subtitle="Decisions made by branch managers and the loan vetting committee, company-wide"
      />

      <Card>
        <DataTable
          columns={[
            { key: "name", header: "Name", sortable: true, accessor: (s: StaffPerformanceItemResponse) => s.full_name },
            {
              key: "role",
              header: "Role",
              accessor: (s) => s.role,
              render: (s) => <Badge tone="brand">{ROLE_LABELS[s.role] ?? s.role.replace(/_/g, " ")}</Badge>,
            },
            { key: "branch", header: "Branch", accessor: (s) => s.branch_name ?? "Company-wide" },
            { key: "decisions", header: "Decisions", sortable: true, accessor: (s) => s.decisions_made },
            {
              key: "approvals",
              header: "Approved",
              sortable: true,
              accessor: (s) => s.approvals,
              render: (s) => <Badge tone="success">{s.approvals}</Badge>,
            },
            {
              key: "rejections",
              header: "Rejected",
              sortable: true,
              accessor: (s) => s.rejections,
              render: (s) => <Badge tone="danger">{s.rejections}</Badge>,
            },
          ]}
          data={performanceQuery.data}
          getRowId={(s) => s.staff_id}
          isLoading={performanceQuery.isLoading}
          isError={performanceQuery.isError}
          searchKeys={["name"]}
          searchPlaceholder="Search staff…"
          emptyMessage="No decisions recorded yet."
        />
      </Card>
    </AppShell>
  );
}
