import { AppShell } from "../../components/AppShell";
import { ReportsView } from "../../components/ReportsView";
import { PageHeader } from "../../components/ui";

export function FinanceReportsPage() {
  return (
    <AppShell>
      <PageHeader title="Reports" subtitle="Disbursed, collected, expenses, and net for any date range" />
      <ReportsView endpoint="/finance/reports" queryKeyPrefix="finance" />
    </AppShell>
  );
}
