import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import type { AuditLogResponse } from "../../schemas/admin";

export function CompanyAuditLogPage() {
  const auditQuery = useQuery({
    queryKey: ["admin", "audit-log"],
    queryFn: () => apiRequest<AuditLogResponse[]>("/admin/audit-log"),
  });

  return (
    <AppShell>
      <PageHeader title="Audit log" subtitle="Every privileged action taken in or on your company — append-only" />

      <Card>
        <DataTable
          columns={[
            {
              key: "created_at",
              header: "When",
              sortable: true,
              accessor: (e: AuditLogResponse) => e.created_at,
              render: (e) => new Date(e.created_at).toLocaleString(),
            },
            { key: "actor", header: "Actor", accessor: (e) => e.actor_email },
            {
              key: "action",
              header: "Action",
              sortable: true,
              accessor: (e) => e.action,
              render: (e) => (
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs">{e.action}</span>
                  {e.is_platform_action ? <Badge tone="brand">Platform</Badge> : null}
                  {e.is_anomaly ? <Badge tone="danger">Anomaly</Badge> : null}
                </div>
              ),
            },
            { key: "entity", header: "Entity", accessor: (e) => `${e.entity_type}${e.entity_id ? ` #${e.entity_id}` : ""}` },
            { key: "reason", header: "Reason", accessor: (e) => e.reason ?? "—" },
          ]}
          data={auditQuery.data}
          getRowId={(e) => e.id}
          isLoading={auditQuery.isLoading}
          isError={auditQuery.isError}
          searchKeys={["actor", "action"]}
          searchPlaceholder="Search by actor or action…"
          emptyMessage="No activity recorded yet."
        />
      </Card>
    </AppShell>
  );
}
