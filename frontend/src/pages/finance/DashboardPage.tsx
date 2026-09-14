import { AppShell } from "../../components/AppShell";
import { EmptyState, PageHeader } from "../../components/ui";

/**
 * CLAUDE.md §14 M10/M17: minimal placeholder — disbursement queue and the
 * financial module (cashbook, income statement, balance sheet, branch
 * profitability — §30) ship in M14/M17. §18: not built = not faked.
 */
export function FinanceDashboardPage() {
  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Cashier / Finance" />
      <EmptyState>
        The disbursement queue and financial reports are coming soon — they ship alongside the
        disbursement and financial-module milestones.
      </EmptyState>
    </AppShell>
  );
}
