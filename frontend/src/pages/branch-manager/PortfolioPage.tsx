import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { Banner, Card, LoadingRow, PageHeader, StatCard } from "../../components/ui";
import type { PortfolioSummaryResponse } from "../../schemas/admin";

export function BranchManagerPortfolioPage() {
  const summaryQuery = useQuery({
    queryKey: ["branch-manager", "portfolio"],
    queryFn: () => apiRequest<PortfolioSummaryResponse>("/branch-manager/portfolio"),
  });

  return (
    <AppShell>
      <PageHeader title="Portfolio" subtitle="Your branch's aggregate performance" />

      {summaryQuery.isLoading ? <LoadingRow /> : null}
      {summaryQuery.isError ? <Banner kind="error">Could not load the portfolio summary</Banner> : null}

      {summaryQuery.data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard label="Total disbursed" value={`KES ${summaryQuery.data.total_disbursed}`} tone="brand" />
            <StatCard label="Total collected" value={`KES ${summaryQuery.data.total_collected}`} tone="success" />
            <StatCard label="Outstanding principal" value={`KES ${summaryQuery.data.outstanding_principal}`} tone="neutral" />
            <StatCard
              label="Portfolio at risk"
              value={`${summaryQuery.data.par_percentage}%`}
              tone={Number(summaryQuery.data.par_percentage) > 0 ? "danger" : "success"}
            />
            <StatCard label="Active borrowers" value={summaryQuery.data.active_borrowers} tone="neutral" />
            <StatCard
              label="Overdue / defaulted"
              value={`${summaryQuery.data.overdue_loans} / ${summaryQuery.data.defaulted_loans}`}
              tone={summaryQuery.data.overdue_loans + summaryQuery.data.defaulted_loans > 0 ? "danger" : "success"}
            />
          </div>

          <Card>
            <div className="flex flex-wrap gap-x-8 gap-y-3 text-sm">
              <div>
                <p className="text-slate-500 dark:text-slate-400">Active loans</p>
                <p className="mt-0.5 font-semibold text-slate-900 dark:text-slate-100">
                  {summaryQuery.data.active_loans}
                </p>
              </div>
              <div>
                <p className="text-slate-500 dark:text-slate-400">Disbursed this month</p>
                <p className="mt-0.5 font-semibold text-slate-900 dark:text-slate-100">
                  {summaryQuery.data.loans_disbursed_this_month}
                </p>
              </div>
              <div>
                <p className="text-slate-500 dark:text-slate-400">As of</p>
                <p className="mt-0.5 font-semibold text-slate-900 dark:text-slate-100">{summaryQuery.data.as_of}</p>
              </div>
            </div>
          </Card>
        </div>
      ) : null}
    </AppShell>
  );
}
