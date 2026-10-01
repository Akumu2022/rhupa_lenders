import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Banner, Card, PageHeader, SectionLabel, StatCard } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import type { StaffActivityItem, StaffDetailResponse, StaffHandledApplication } from "../../schemas/staff";
import { applicationStatusLabel, applicationStatusTone } from "../customer/shared";
import type { LoanApplicationResponse } from "../../schemas/loan";
import { ResetStaffPasswordAction, StatusToggle } from "./UsersPage";

function DetailRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-medium text-slate-900 dark:text-slate-100">{value ?? "—"}</dd>
    </div>
  );
}

const INVOLVEMENT_LABELS: Record<StaffHandledApplication["involvement"], string> = {
  prepared: "Prepared",
  decided: "Decided",
  reviewed: "Reviewed a stage",
};

/** Remount per staff id so table state never leaks between two people. */
export function StaffDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  return <StaffDetailView key={userId} userId={Number(userId)} />;
}

function StaffDetailView({ userId }: { userId: number }) {
  const navigate = useNavigate();
  const isValidId = Number.isFinite(userId);
  const staffQuery = useQuery({
    queryKey: ["staff", userId],
    queryFn: () => apiRequest<StaffDetailResponse>(`/staff/${userId}`),
    enabled: isValidId,
  });
  const staff = staffQuery.data;

  return (
    <AppShell>
      <PageHeader
        title={staff ? staff.full_name : "Staff member"}
        subtitle={staff ? staff.role.replace(/_/g, " ") : undefined}
        actions={
          staff ? (
            <div className="flex gap-2">
              <StatusToggle staff={{ ...staff, company_id: null }} />
              <ResetStaffPasswordAction staff={{ ...staff, company_id: null }} />
            </div>
          ) : null
        }
      />

      {!isValidId ? <Banner kind="error">Staff member not found.</Banner> : null}
      {isValidId && staffQuery.isLoading ? <Card>Loading…</Card> : null}
      {isValidId && staffQuery.isError ? <Banner kind="error">Could not load this staff member.</Banner> : null}

      {staff ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <StatCard label="Applications handled" value={staff.applications.length} tone="brand" />
            <StatCard label="Assigned customers" value={staff.assigned_customers} tone="neutral" />
            <StatCard label="Recent actions" value={staff.recent_activity.length} tone="neutral" />
          </div>

          <Card>
            <div className="mb-3 flex items-center justify-between">
              <SectionLabel>Details</SectionLabel>
              <Badge tone={staff.is_active ? "success" : "neutral"}>{staff.is_active ? "Active" : "Inactive"}</Badge>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <DetailRow label="Full name" value={staff.full_name} />
              <DetailRow label="Email" value={staff.email} />
              <DetailRow label="Role" value={staff.role.replace(/_/g, " ")} />
              <DetailRow label="Branch" value={staff.branch_name ?? "Company-wide"} />
            </dl>
          </Card>

          <Card>
            <SectionLabel>Applications they handled</SectionLabel>
            <DataTable
              columns={[
                { key: "customer", header: "Customer", sortable: true, accessor: (a: StaffHandledApplication) => a.customer_full_name },
                { key: "product", header: "Product", accessor: (a) => a.loan_product_name },
                {
                  key: "amount",
                  header: "Amount",
                  sortable: true,
                  accessor: (a) => Number(a.amount_requested),
                  render: (a) => `KES ${a.amount_requested}`,
                },
                { key: "involvement", header: "Their part", accessor: (a) => INVOLVEMENT_LABELS[a.involvement] },
                {
                  key: "status",
                  header: "Status",
                  accessor: (a) => a.status,
                  render: (a) => {
                    const s = a.status as LoanApplicationResponse["status"];
                    return <Badge tone={applicationStatusTone(s)}>{applicationStatusLabel(s)}</Badge>;
                  },
                },
                {
                  key: "created_at",
                  header: "Submitted",
                  sortable: true,
                  accessor: (a) => a.created_at,
                  render: (a) => new Date(a.created_at).toLocaleDateString(),
                },
              ]}
              data={staff.applications}
              getRowId={(a) => a.id}
              searchKeys={["customer"]}
              searchPlaceholder="Search by customer…"
              emptyMessage="No applications prepared or decided by this staff member yet."
              onRowClick={(a) => navigate(`/admin/customers/${a.customer_id}`)}
            />
          </Card>

          <Card>
            <SectionLabel>Recent activity</SectionLabel>
            <DataTable
              columns={[
                {
                  key: "created_at",
                  header: "When",
                  sortable: true,
                  accessor: (e: StaffActivityItem) => e.created_at,
                  render: (e) => new Date(e.created_at).toLocaleString(),
                },
                { key: "action", header: "Action", accessor: (e) => e.action },
                {
                  key: "entity",
                  header: "On",
                  accessor: (e) => `${e.entity_type}${e.entity_id ? ` #${e.entity_id}` : ""}`,
                },
                { key: "reason", header: "Details", accessor: (e) => e.reason ?? "—" },
              ]}
              data={staff.recent_activity}
              getRowId={(e) => e.id}
              emptyMessage="No recorded actions yet."
            />
          </Card>
        </div>
      ) : null}
    </AppShell>
  );
}
