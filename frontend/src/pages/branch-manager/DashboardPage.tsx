import { AppShell } from "../../components/AppShell";
import { EmptyState, PageHeader } from "../../components/ui";

/**
 * CLAUDE.md §14 M10/M19: minimal placeholder — the client PRD's full
 * "Good Morning" daily-target dashboard (§26, §29: target/collected/
 * achievement, customers due/paid, overdue, portfolio, PAR) ships once
 * collections (M15) and the multi-stage approval chain (M13) exist to feed
 * it. §18: not built = not faked.
 */
export function BranchManagerDashboardPage() {
  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Branch command dashboard" />
      <EmptyState>
        The full branch dashboard (daily target, collections, overdue accounts, PAR) is coming
        soon — it ships alongside the collections and approval-workflow milestones.
      </EmptyState>
    </AppShell>
  );
}
