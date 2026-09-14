import { AppShell } from "../../components/AppShell";
import { EmptyState, PageHeader } from "../../components/ui";

/**
 * CLAUDE.md §14 M10/M18: minimal placeholder — organization-wide aggregate
 * reporting (§30) ships with the management-reporting milestone. §18: not
 * built = not faked.
 */
export function ManagementDashboardPage() {
  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Organization-wide reporting" />
      <EmptyState>
        Organization-wide reports (portfolio, PAR, collections, branch ranking) are coming soon
        — they ship alongside the management-reporting milestone.
      </EmptyState>
    </AppShell>
  );
}
