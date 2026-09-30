import { useState } from "react";
import type { ReactNode } from "react";
import { AppShell } from "./AppShell";
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
} from "./analytics";
import { Drawer } from "./Drawer";
import { Badge, Banner, Card, PageHeader, SectionLabel } from "./ui";
import { SORTED_STAGES, addDecimal, formatKES, formatKESShort, pctString, sumDecimal } from "../schemas/analytics";

export interface AwaitingOverride {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  to: string;
}

/** Branch-level loan dashboard shared by the credit officer and the branch
 * manager (CLAUDE.md §9/§29): what's been sorted, what's waiting on a
 * decision, what's due and overdue. Scope (branch, or the officer's own
 * applications with `mine`) is decided server-side from the logged-in user;
 * this component only chooses wording and where the tiles link. */
export function BranchLoanDashboard({
  subtitle,
  listBase,
  mine = false,
  headerExtras,
  awaiting,
}: {
  subtitle: string;
  /** The all-stages loans list the tiles and pipeline rows drill into. */
  listBase: string;
  mine?: boolean;
  headerExtras?: ReactNode;
  /** Replace the default "awaiting a decision" tile, e.g. with the branch
   * manager's own actionable queue. */
  awaiting?: AwaitingOverride;
}) {
  const range = useDateRange();
  const query = useDashboard(range, { mine });
  const [openApplication, setOpenApplication] = useState<number | null>(null);
  const d = query.data;
  const loading = query.isLoading;

  const sorted = d?.pipeline.filter((s) => SORTED_STAGES.includes(s.stage)) ?? [];
  const sortedCount = sorted.reduce((n, s) => n + s.count, 0);
  const rejected = d?.pipeline.find((s) => s.stage === "rejected");

  return (
    <AppShell>
      <PageHeader
        title="Dashboard"
        subtitle={subtitle}
        actions={
          <div className="flex flex-wrap items-center gap-3">
            {headerExtras}
            <DateRangeBar range={range} />
          </div>
        }
      />

      {query.isError ? <Banner kind="error">Couldn't load the dashboard.</Banner> : null}
      {d?.scope === "unassigned" ? (
        <div className="mb-4">
          <Banner kind="info">
            Your account isn't assigned to a branch yet, so you're seeing applications that also have no branch. Ask
            your system administrator to assign you to a branch.
          </Banner>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiTile
          loading={loading}
          tone="brand"
          icon="checkCircle"
          label="Approved & sorted"
          value={sortedCount.toLocaleString()}
          sub={d ? <>{formatKESShort(sumDecimal(sorted.map((s) => s.amount)))} approved this period</> : null}
          to={`${listBase}?stage=sorted`}
        />
        <KpiTile
          loading={loading}
          tone="amber"
          icon="clipboardList"
          label={awaiting?.label ?? "Awaiting a decision"}
          value={awaiting ? awaiting.value : (d?.queues.in_review_count.toLocaleString() ?? "…")}
          sub={awaiting ? awaiting.sub : d ? <>{formatKESShort(d.queues.in_review_amount)} requested · with branch manager/committee</> : null}
          to={awaiting?.to ?? `${listBase}?stage=in_review`}
        />
        <KpiTile
          loading={loading}
          tone={d && d.portfolio.overdue_loans + d.portfolio.defaulted_loans > 0 ? "danger" : "success"}
          icon="bell"
          label="Overdue loans"
          value={d ? (d.portfolio.overdue_loans + d.portfolio.defaulted_loans).toLocaleString() : "…"}
          sub={d ? <>{formatKESShort(d.portfolio.arrears_amount)} in arrears · PAR {d.portfolio.par_pct}%</> : null}
          to={`${listBase}?stage=overdue`}
        />
        <KpiTile
          loading={loading}
          tone="neutral"
          icon="documentText"
          label="Rejected"
          value={rejected?.count.toLocaleString() ?? "…"}
          sub={rejected ? <>{formatKESShort(rejected.amount)} declined this period</> : null}
          to={`${listBase}?stage=rejected`}
        />
      </div>

      {d ? (
        <>
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card>
              <SectionLabel>Due today</SectionLabel>
              <p className="text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-50">{formatKES(d.due.today_amount)}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {d.due.today_count} customer{d.due.today_count === 1 ? "" : "s"} due
              </p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <Badge tone="success">Paid {d.due.today_paid}</Badge>
                <Badge tone="warning">Partial {d.due.today_partial}</Badge>
                <Badge tone="danger">Unpaid {d.due.today_unpaid}</Badge>
              </div>
              <div className="mt-4">
                <RateMeter
                  label="Collected today"
                  pct={pctString(d.due.today_collected, d.due.today_amount)}
                  numerator={d.due.today_collected}
                  denominator={d.due.today_amount}
                  tone="success"
                />
              </div>
            </Card>

            <Card>
              <SectionLabel>Collections this period</SectionLabel>
              <RateMeter
                label="Collection rate"
                pct={d.flows.collection_rate_pct}
                numerator={d.flows.paid_against_due}
                denominator={d.flows.due_amount}
                tone={Number(d.flows.collection_rate_pct) >= 90 ? "success" : Number(d.flows.collection_rate_pct) >= 70 ? "warning" : "danger"}
                hint="of instalments that fell due"
              />
              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <Stat label="Collected" value={formatKESShort(d.flows.collected_amount)} />
                <Stat label="Disbursed" value={formatKESShort(d.flows.disbursed_amount)} />
                <Stat label="Due next 30 days" value={formatKESShort(d.due.next_30_days_amount)} />
                <Stat label="Penalties charged" value={formatKESShort(d.flows.penalties_charged)} />
              </dl>
            </Card>

            <Card>
              <SectionLabel>Portfolio now</SectionLabel>
              <p className="text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-50">{formatKES(d.portfolio.outstanding_total)}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                outstanding across {d.portfolio.active_borrowers} borrower{d.portfolio.active_borrowers === 1 ? "" : "s"}
              </p>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
                <Stat label="Principal" value={formatKESShort(d.portfolio.outstanding_principal)} />
                <Stat label="Interest" value={formatKESShort(d.portfolio.outstanding_interest)} />
                <Stat label="Penalties" value={formatKESShort(d.portfolio.outstanding_penalties)} />
              </dl>
              <div className="mt-4">
                <RateMeter
                  label="Repayment progress (all loans)"
                  pct={d.portfolio.repayment_progress_pct}
                  numerator={d.portfolio.total_repaid_all_time}
                  denominator={addDecimal(d.portfolio.total_repaid_all_time, d.portfolio.outstanding_total)}
                  tone="brand"
                />
              </div>
            </Card>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
            <Card className="lg:col-span-8">
              <SectionLabel>Disbursed vs collected</SectionLabel>
              <FlowChart data={d} />
            </Card>
            <Card className="lg:col-span-4">
              <SectionLabel>Applications this period</SectionLabel>
              <PipelineList stages={d.pipeline} linkBase={listBase} />
            </Card>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <SectionLabel>Due in the next 7 days</SectionLabel>
              <NextDaysChart data={d} />
            </Card>
            <Card>
              <SectionLabel>Arrears aging</SectionLabel>
              <AgingChart data={d} />
            </Card>
          </div>

          <Card className="mt-4">
            <SectionLabel>Follow up: overdue and due this week</SectionLabel>
            <DueListTable items={d.due_list} onOpen={setOpenApplication} />
          </Card>
        </>
      ) : null}

      <Drawer open={openApplication !== null} onClose={() => setOpenApplication(null)} title="Loan history">
        {openApplication !== null ? <LoanTimeline applicationId={openApplication} /> : null}
      </Drawer>
    </AppShell>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-semibold tabular-nums text-slate-900 dark:text-slate-50">{value}</dd>
    </div>
  );
}
