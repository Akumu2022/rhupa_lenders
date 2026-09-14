import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { HeroStat, LinkTile, PageHeader, StatCard } from "../../components/ui";
import type { PendingDisbursementResponse } from "../../schemas/credit";
import type { FinancialsResponse } from "../../schemas/finance";

/** CLAUDE.md §28/§30 (M14/M17): cashier/finance officer's command
 * dashboard — disbursement queue depth + a 30-day income/expense glance. */
export function FinanceDashboardPage() {
  const pendingQuery = useQuery({
    queryKey: ["finance", "disbursements"],
    queryFn: () => apiRequest<PendingDisbursementResponse[]>("/finance/disbursements"),
  });
  const financialsQuery = useQuery({
    queryKey: ["finance", "financials"],
    queryFn: () => apiRequest<FinancialsResponse>("/finance/financials"),
  });

  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Disbursements, cashbook, and reports" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <HeroStat
            label="Ready to disburse"
            value={pendingQuery.data?.length ?? "…"}
            tone="brand"
            subtext="Approved loans awaiting disbursement"
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:col-span-8">
          <StatCard
            label="30-day expenses"
            value={financialsQuery.data ? `KES ${financialsQuery.data.total_expenses}` : "…"}
            tone="neutral"
          />
          <StatCard
            label="30-day net"
            value={financialsQuery.data ? `KES ${financialsQuery.data.net}` : "…"}
            tone={financialsQuery.data && Number(financialsQuery.data.net) >= 0 ? "success" : "danger"}
          />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <LinkTile to="/finance/disbursements" icon="banknotes" label="Disbursements" description="Approved loans ready to disburse" />
        <LinkTile to="/finance/financials" icon="chartBar" label="Financials" description="Income, expenses, and the cashbook" />
        <LinkTile to="/finance/reports" icon="archiveBox" label="Reports" description="Date-range summary reports" />
      </div>
    </AppShell>
  );
}
