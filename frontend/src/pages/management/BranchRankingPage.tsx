import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Badge, Card, PageHeader } from "../../components/ui";
import { DataTable } from "../../components/DataTable";
import type { BranchRankingItemResponse } from "../../schemas/management";

export function ManagementBranchRankingPage() {
  const rankingQuery = useQuery({
    queryKey: ["management", "branch-ranking"],
    queryFn: () => apiRequest<BranchRankingItemResponse[]>("/management/branch-ranking"),
  });

  return (
    <AppShell>
      <PageHeader title="Branch ranking" subtitle="Branches ranked by total disbursed, company-wide" />

      <Card>
        <DataTable
          columns={[
            { key: "branch", header: "Branch", sortable: true, accessor: (b: BranchRankingItemResponse) => b.branch_name },
            { key: "code", header: "Code", accessor: (b) => b.branch_code },
            {
              key: "disbursed",
              header: "Total disbursed",
              sortable: true,
              accessor: (b) => Number(b.total_disbursed),
              render: (b) => `KES ${b.total_disbursed}`,
            },
            {
              key: "outstanding",
              header: "Outstanding principal",
              sortable: true,
              accessor: (b) => Number(b.outstanding_principal),
              render: (b) => `KES ${b.outstanding_principal}`,
            },
            {
              key: "par",
              header: "PAR",
              sortable: true,
              accessor: (b) => Number(b.par_percentage),
              render: (b) => <Badge tone={Number(b.par_percentage) > 0 ? "danger" : "success"}>{b.par_percentage}%</Badge>,
            },
            { key: "active_loans", header: "Active loans", sortable: true, accessor: (b) => b.active_loans },
          ]}
          data={rankingQuery.data}
          getRowId={(b) => b.branch_id}
          isLoading={rankingQuery.isLoading}
          isError={rankingQuery.isError}
          searchKeys={["branch"]}
          searchPlaceholder="Search branches…"
          emptyMessage="No active branches yet."
        />
      </Card>
    </AppShell>
  );
}
