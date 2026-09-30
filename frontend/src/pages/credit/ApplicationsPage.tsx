import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiRequest } from "../../api/client";
import { AppShell } from "../../components/AppShell";
import { LoanTimeline } from "../../components/analytics";
import { DataTable } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { GuarantorsCollateralPanel } from "../../components/GuarantorsCollateralPanel";
import { Badge, Card, PageHeader, SectionLabel } from "../../components/ui";
import {
  SORTED_STAGES,
  STAGE_META,
  chartNumber,
  formatDate,
  formatDateTime,
  formatKES,
  type ApplicationListItem,
  type Stage,
} from "../../schemas/analytics";

type Tab = "all" | "in_review" | "sorted" | "awaiting_disbursement" | "active" | "overdue" | "repaid" | "rejected";

const TABS: { value: Tab; label: string; match: (s: Stage) => boolean }[] = [
  { value: "all", label: "All", match: () => true },
  { value: "sorted", label: "Approved & sorted", match: (s) => SORTED_STAGES.includes(s) },
  { value: "in_review", label: "Awaiting decision", match: (s) => s === "in_review" },
  { value: "awaiting_disbursement", label: "Awaiting disbursement", match: (s) => s === "awaiting_disbursement" },
  { value: "active", label: "Active", match: (s) => s === "active" },
  { value: "overdue", label: "Overdue", match: (s) => s === "overdue" || s === "defaulted" },
  { value: "repaid", label: "Repaid", match: (s) => s === "repaid" },
  { value: "rejected", label: "Rejected", match: (s) => s === "rejected" },
];

/** Every application in the officer's branch at every stage — previously
 * this page only listed in-review items, so an application vanished the
 * moment it was approved. `mode="mine"` (the My Portfolio page) narrows to
 * applications this officer prepared (server-side `prepared_by`). Clicking a
 * row opens the full movement history; while still in review, the officer
 * can also attach guarantors/collateral (CLAUDE.md §27). */
export function CreditApplicationsPage({
  mode = "branch",
  title,
  subtitle,
  canEditGuarantors = true,
}: {
  mode?: "branch" | "mine";
  title?: string;
  subtitle?: string;
  /** Only the credit officer prepares applications (CLAUDE.md §8). */
  canEditGuarantors?: boolean;
}) {
  const mine = mode === "mine";
  const [params, setParams] = useSearchParams();
  const tab = (params.get("stage") as Tab | null) ?? "all";
  const [selected, setSelected] = useState<ApplicationListItem | null>(null);

  const query = useQuery({
    queryKey: ["analytics", "applications", mine],
    queryFn: () => apiRequest<ApplicationListItem[]>(`/analytics/applications${mine ? "?mine=true" : ""}`),
  });

  const counts = useMemo(() => {
    const out: Record<Tab, number> = { all: 0, in_review: 0, sorted: 0, awaiting_disbursement: 0, active: 0, overdue: 0, repaid: 0, rejected: 0 };
    for (const a of query.data ?? []) for (const t of TABS) if (t.match(a.stage)) out[t.value] += 1;
    return out;
  }, [query.data]);

  const activeTab = TABS.find((t) => t.value === tab) ?? TABS[0];
  const rows = useMemo(() => (query.data ?? []).filter((a) => activeTab.match(a.stage)), [query.data, activeTab]);

  function setTab(next: Tab) {
    const p = new URLSearchParams(params);
    if (next === "all") p.delete("stage");
    else p.set("stage", next);
    setParams(p, { replace: true });
  }

  return (
    <AppShell>
      <PageHeader
        title={title ?? (mine ? "My portfolio" : "Applications")}
        subtitle={
          subtitle ??
          (mine
            ? "Every application you prepared, from submission to repayment"
            : "Every application in your branch, from submission to repayment")
        }
      />

      <div className="mb-4 flex flex-wrap gap-2" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={t.value === activeTab.value}
            onClick={() => setTab(t.value)}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
              t.value === activeTab.value
                ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700 dark:hover:bg-slate-800"
            }`}
          >
            {t.label} <span className="ml-1 tabular-nums opacity-70">{counts[t.value]}</span>
          </button>
        ))}
      </div>

      <Card>
        <DataTable
          columns={[
            { key: "customer", header: "Customer", sortable: true, accessor: (a: ApplicationListItem) => a.customer_full_name },
            { key: "product", header: "Product", accessor: (a) => a.loan_product_name },
            {
              key: "amount",
              header: "Amount",
              sortable: true,
              accessor: (a) => chartNumber(a.principal ?? a.amount_requested),
              render: (a) => <span className="tabular-nums">{formatKES(a.principal ?? a.amount_requested)}</span>,
            },
            {
              key: "stage",
              header: "Status",
              accessor: (a) => a.stage,
              render: (a) => {
                const meta = STAGE_META[a.stage];
                return (
                  <Badge tone={meta.tone}>
                    {meta.label}
                    {a.stage === "overdue" && a.days_past_due > 0 ? ` · ${a.days_past_due}d` : ""}
                  </Badge>
                );
              },
            },
            {
              key: "outstanding",
              header: "Outstanding",
              sortable: true,
              accessor: (a) => (a.outstanding_balance ? chartNumber(a.outstanding_balance) : -1),
              render: (a) => <span className="tabular-nums">{a.outstanding_balance ? formatKES(a.outstanding_balance) : "—"}</span>,
            },
            {
              key: "next_due",
              header: "Next due",
              sortable: true,
              accessor: (a) => a.next_due_date ?? "9999",
              render: (a) =>
                a.next_due_date ? (
                  <span className={a.days_past_due > 0 ? "font-medium text-rose-600 dark:text-rose-400" : ""}>{formatDate(a.next_due_date)}</span>
                ) : (
                  "—"
                ),
            },
            ...(mine ? [] : [{ key: "prepared", header: "Prepared by", accessor: (a: ApplicationListItem) => a.prepared_by_name ?? "Self-service" }]),
            {
              key: "created_at",
              header: "Submitted",
              sortable: true,
              accessor: (a) => a.created_at,
              render: (a) => formatDateTime(a.created_at),
            },
          ]}
          data={rows}
          getRowId={(a) => a.id}
          isLoading={query.isLoading}
          isError={query.isError}
          searchKeys={["customer", "product"]}
          searchPlaceholder="Search by customer or product…"
          emptyMessage={activeTab.value === "all" ? "No applications yet." : `Nothing in “${activeTab.label}”.`}
          onRowClick={(a) => setSelected(a)}
          rowActions={() => <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">History →</span>}
        />
      </Card>

      <Drawer open={selected !== null} onClose={() => setSelected(null)} title={selected ? selected.customer_full_name : ""}>
        {selected ? (
          <div className="space-y-6">
            <LoanTimeline applicationId={selected.id} />
            {canEditGuarantors && selected.stage === "in_review" ? (
              <div>
                <SectionLabel>Guarantors & collateral</SectionLabel>
                <GuarantorsCollateralPanel applicationId={selected.id} editable />
              </div>
            ) : null}
          </div>
        ) : null}
      </Drawer>
    </AppShell>
  );
}
