import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { PortfolioView } from "../../components/PortfolioView";
import { BarList, Card, EmptyState, SectionLabel } from "../../components/ui";
import { chartNumber, formatKESShort } from "../../schemas/analytics";
import type { BranchRankingItemResponse } from "../../schemas/management";

/** CLAUDE.md §9/§30: management — organization-wide, aggregates only, no
 * individual customer PII. The same shared figures as every other
 * dashboard, plus the branch ranking. */
export function ManagementDashboardPage() {
  const rankingQuery = useQuery({
    queryKey: ["management", "branch-ranking"],
    queryFn: () => apiRequest<BranchRankingItemResponse[]>("/management/branch-ranking"),
  });
  const topBranches = (rankingQuery.data ?? []).slice(0, 5);

  return (
    <PortfolioView title="Dashboard" subtitle="Organization-wide loan book and performance">
      <Card className="mt-4">
        <SectionLabel>Top branches by disbursed volume</SectionLabel>
        {topBranches.length === 0 ? (
          <EmptyState>No active branches yet.</EmptyState>
        ) : (
          <BarList
            items={topBranches.map((b) => ({
              label: `${b.branch_name} · PAR ${b.par_percentage}%`,
              value: chartNumber(b.total_disbursed),
              tone: "brand" as const,
            }))}
            formatValue={(v) => formatKESShort(String(v))}
          />
        )}
      </Card>
    </PortfolioView>
  );
}
