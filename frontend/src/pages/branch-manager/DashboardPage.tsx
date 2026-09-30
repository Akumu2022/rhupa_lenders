import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { BranchLoanDashboard } from "../../components/BranchLoanDashboard";
import type { BranchQueueItemResponse } from "../../schemas/branchManager";
import { formatKESShort, sumDecimal } from "../../schemas/analytics";

/** Branch manager command dashboard (CLAUDE.md §9/§26/§29): the same
 * branch-scoped figures the credit officer sees, but "awaiting" is the
 * manager's own actionable queue (branch review only — escalated items sit
 * with the committee), linking straight to where they decide. */
export function BranchManagerDashboardPage() {
  const queueQuery = useQuery({
    queryKey: ["branch-manager", "queue"],
    queryFn: () => apiRequest<BranchQueueItemResponse[]>("/branch-manager/queue"),
  });
  const queue = queueQuery.data;
  const overLimit = queue?.filter((a) => a.over_limit).length ?? 0;

  return (
    <BranchLoanDashboard
      subtitle="Your branch — decisions, loans, and what's due"
      listBase="/branch-manager/loans"
      awaiting={{
        label: "Awaiting your decision",
        value: queue ? queue.length.toLocaleString() : "…",
        sub: queue ? (
          <>
            {formatKESShort(sumDecimal(queue.map((a) => a.amount_requested)))} requested
            {overLimit > 0 ? ` · ${overLimit} above your limit` : " · all within your limit"}
          </>
        ) : null,
        to: "/branch-manager/applications",
      }}
    />
  );
}
