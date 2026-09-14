import { AppShell } from "../../components/AppShell";
import { ReportsView } from "../../components/ReportsView";
import { PageHeader } from "../../components/ui";

export function ManagementReportsPage() {
  return (
    <AppShell>
      <PageHeader title="Reports" subtitle="Company-wide disbursed, collected, expenses, and net for any date range" />
      <ReportsView endpoint="/management/reports" queryKeyPrefix="management" />
    </AppShell>
  );
}
