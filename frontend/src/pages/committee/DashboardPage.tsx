import { AppShell } from "../../components/AppShell";
import { EmptyState, PageHeader } from "../../components/ui";

/**
 * CLAUDE.md §14 M10/M13: minimal placeholder — the committee queue (§26)
 * ships with the multi-stage approval workflow milestone. §18: not built =
 * not faked.
 */
export function CommitteeDashboardPage() {
  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Loan vetting committee" />
      <EmptyState>
        The committee review queue is coming soon — applications above a branch's delegated
        limit will land here once the multi-stage approval workflow ships.
      </EmptyState>
    </AppShell>
  );
}
