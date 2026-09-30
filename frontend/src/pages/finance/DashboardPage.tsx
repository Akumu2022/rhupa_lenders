import { useState } from "react";
import { AppShell } from "../../components/AppShell";
import {
  AgingChart,
  DateRangeBar,
  DueListTable,
  FlowChart,
  KpiTile,
  LoanTimeline,
  NextDaysChart,
  PipelineList,
  RateMeter,
  useDashboard,
  useDateRange,
} from "../../components/analytics";
import { Drawer } from "../../components/Drawer";
import { Banner, Card, PageHeader, SectionLabel } from "../../components/ui";
import { addDecimal, formatKES, formatKESShort, type StageCount } from "../../schemas/analytics";

/** Cashier/finance officer dashboard (CLAUDE.md §28/§30): money out, money
 * in, what's still owed, and how well the book is repaying — company-wide.
 * Every figure is computed server-side (GET /analytics/dashboard). */
export function FinanceDashboardPage() {
  const range = useDateRange();
  const query = useDashboard(range);
  const [openApplication, setOpenApplication] = useState<number | null>(null);
  const d = query.data;
  const loading = query.isLoading;

  // Finance's four-way status view: pending / approved (not yet paid out) /
  // disbursed (any post-payout state) / rejected.
  const statusBreakdown: StageCount[] = d
    ? (() => {
        const get = (stage: string) => d.pipeline.find((s) => s.stage === stage) ?? { stage, count: 0, amount: "0.00" };
        const disbursed = ["active", "overdue", "defaulted", "repaid"].map(get);
        return [
          get("in_review") as StageCount,
          get("awaiting_disbursement") as StageCount,
          {
            stage: "active",
            count: disbursed.reduce((n, s) => n + s.count, 0),
            amount: disbursed.reduce((sum, s) => addDecimal(sum, s.amount), "0.00"),
          },
          get("rejected") as StageCount,
        ];
      })()
    : [];

  const collectionTone = (pct: string) => (Number(pct) >= 90 ? "success" : Number(pct) >= 70 ? "warning" : "danger");

  return (
    <AppShell>
      <PageHeader title="Dashboard" subtitle="Disbursements, repayments, and loan book performance" actions={<DateRangeBar range={range} />} />

      {query.isError ? <Banner kind="error">Couldn't load the dashboard.</Banner> : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiTile
          loading={loading}
          tone="brand"
          icon="banknotes"
          label="Total disbursed"
          value={d ? formatKESShort(d.flows.disbursed_amount) : "…"}
          sub={
            d ? (
              <>
                {d.flows.disbursed_count} loan{d.flows.disbursed_count === 1 ? "" : "s"} this period · {formatKESShort(d.portfolio.total_disbursed_all_time)} all time
              </>
            ) : null
          }
          to="/finance/loans?stage=sorted"
        />
        <KpiTile
          loading={loading}
          tone="success"
          icon="wallet"
          label="Total repaid"
          value={d ? formatKESShort(d.flows.collected_amount) : "…"}
          sub={
            d ? (
              <>
                {d.flows.collected_count} payment{d.flows.collected_count === 1 ? "" : "s"} this period · {formatKESShort(d.portfolio.total_repaid_all_time)} all time
              </>
            ) : null
          }
          to="/finance/loans?stage=repaid"
        />
        <KpiTile
          loading={loading}
          tone="neutral"
          icon="chartBar"
          label="Outstanding"
          value={d ? formatKESShort(d.portfolio.outstanding_total) : "…"}
          sub={
            d ? (
              <>
                Principal {formatKESShort(d.portfolio.outstanding_principal)} · Interest {formatKESShort(d.portfolio.outstanding_interest)} ·
                Penalties {formatKESShort(d.portfolio.outstanding_penalties)}
              </>
            ) : null
          }
          to="/finance/loans?stage=active"
        />
        <KpiTile
          loading={loading}
          tone="amber"
          icon="clipboardList"
          label="Ready to disburse"
          value={d?.queues.awaiting_disbursement_count.toLocaleString() ?? "…"}
          sub={d ? <>{formatKESShort(d.queues.awaiting_disbursement_amount)} approved, awaiting payout</> : null}
          to="/finance/disbursements"
        />
      </div>

      {d ? (
        <>
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card>
              <SectionLabel>Repayment performance</SectionLabel>
              <div className="space-y-4">
                <RateMeter
                  label="Collection rate (this period)"
                  pct={d.flows.collection_rate_pct}
                  numerator={d.flows.paid_against_due}
                  denominator={d.flows.due_amount}
                  tone={collectionTone(d.flows.collection_rate_pct)}
                  hint="paid of what fell due"
                />
                <RateMeter
                  label="Loan book repaid (all time)"
                  pct={d.portfolio.repayment_progress_pct}
                  numerator={d.portfolio.total_repaid_all_time}
                  denominator={addDecimal(d.portfolio.total_repaid_all_time, d.portfolio.outstanding_total)}
                  tone="brand"
                />
                <div className="flex items-baseline justify-between border-t border-slate-100 pt-3 dark:border-slate-800">
                  <span className="text-xs font-medium text-slate-600 dark:text-slate-300">Portfolio at risk (PAR)</span>
                  <span
                    className={`text-lg font-bold tabular-nums ${Number(d.portfolio.par_pct) > 10 ? "text-rose-600 dark:text-rose-400" : "text-slate-900 dark:text-slate-50"}`}
                  >
                    {d.portfolio.par_pct}%
                  </span>
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {d.portfolio.overdue_loans} overdue · {d.portfolio.defaulted_loans} defaulted · {formatKESShort(d.portfolio.arrears_amount)} in arrears
                </p>
              </div>
            </Card>

            <Card>
              <SectionLabel>Applications this period</SectionLabel>
              <PipelineList
                stages={statusBreakdown}
                labels={{ in_review: "Pending decision", awaiting_disbursement: "Approved, not yet disbursed", active: "Disbursed", rejected: "Declined / rejected" }}
              />
              <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                “Disbursed” counts every paid-out loan: active, overdue, defaulted, or repaid.
              </p>
            </Card>

            <Card>
              <SectionLabel>Cash expected in</SectionLabel>
              <dl className="space-y-3 text-sm">
                <Row label="Due today" value={formatKES(d.due.today_amount)} sub={`${formatKESShort(d.due.today_collected)} collected so far`} />
                <Row
                  label="Next 7 days"
                  value={formatKES(d.due.next_7_days.reduce((sum, x) => addDecimal(sum, x.amount), "0.00"))}
                  sub={`${d.due.next_7_days.reduce((n, x) => n + x.count, 0)} instalments`}
                />
                <Row label="Next 30 days" value={formatKES(d.due.next_30_days_amount)} sub={`${d.due.next_30_days_count} instalments`} />
                <Row label="Overdue (arrears)" value={formatKES(d.portfolio.arrears_amount)} sub={`${d.due.overdue_installments} instalments`} danger />
              </dl>
            </Card>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
            <Card className="lg:col-span-8">
              <SectionLabel>Disbursed vs collected</SectionLabel>
              <FlowChart data={d} />
            </Card>
            <Card className="lg:col-span-4">
              <SectionLabel>Due in the next 7 days</SectionLabel>
              <NextDaysChart data={d} />
            </Card>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
            <Card className="lg:col-span-5">
              <SectionLabel>Arrears aging</SectionLabel>
              <AgingChart data={d} />
            </Card>
            <Card className="lg:col-span-7">
              <SectionLabel>Overdue and due this week</SectionLabel>
              <DueListTable items={d.due_list} onOpen={setOpenApplication} />
            </Card>
          </div>
        </>
      ) : null}

      <Drawer open={openApplication !== null} onClose={() => setOpenApplication(null)} title="Loan history">
        {openApplication !== null ? <LoanTimeline applicationId={openApplication} /> : null}
      </Drawer>
    </AppShell>
  );
}

function Row({ label, value, sub, danger }: { label: string; value: string; sub?: string; danger?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <div>
        <dt className="text-slate-600 dark:text-slate-300">{label}</dt>
        {sub ? <dd className="text-xs text-slate-500 dark:text-slate-400">{sub}</dd> : null}
      </div>
      <dd className={`font-semibold tabular-nums ${danger ? "text-rose-600 dark:text-rose-400" : "text-slate-900 dark:text-slate-50"}`}>{value}</dd>
    </div>
  );
}
