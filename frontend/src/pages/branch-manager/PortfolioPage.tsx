import { AppShell } from "../../components/AppShell";
import {
  AgingChart,
  DateRangeBar,
  FlowChart,
  KpiTile,
  PipelineList,
  RateMeter,
  useDashboard,
  useDateRange,
} from "../../components/analytics";
import { Banner, Card, PageHeader, SectionLabel } from "../../components/ui";
import { addDecimal, formatKESShort } from "../../schemas/analytics";

/** Branch portfolio (CLAUDE.md §29): the loan book as it stands now, plus
 * money in/out over the chosen range. Same server figures as the dashboard,
 * so the two pages can never disagree. */
export function BranchManagerPortfolioPage() {
  const range = useDateRange();
  const query = useDashboard(range);
  const d = query.data;
  const loading = query.isLoading;
  const atRisk = d ? d.portfolio.overdue_loans + d.portfolio.defaulted_loans : 0;

  return (
    <AppShell>
      <PageHeader title="Portfolio" subtitle="Your branch's loan book" actions={<DateRangeBar range={range} />} />
      {query.isError ? <Banner kind="error">Couldn't load the portfolio.</Banner> : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiTile
          loading={loading}
          tone="brand"
          icon="chartBar"
          label="Outstanding"
          value={d ? formatKESShort(d.portfolio.outstanding_total) : "…"}
          sub={d ? <>{d.portfolio.active_borrowers} active borrowers</> : null}
          to="/branch-manager/loans?stage=active"
        />
        <KpiTile
          loading={loading}
          tone={atRisk > 0 ? "danger" : "success"}
          icon="bell"
          label="Portfolio at risk"
          value={d ? `${d.portfolio.par_pct}%` : "…"}
          sub={d ? <>{atRisk} loans overdue/defaulted · {formatKESShort(d.portfolio.arrears_amount)} in arrears</> : null}
          to="/branch-manager/loans?stage=overdue"
        />
        <KpiTile
          loading={loading}
          tone="neutral"
          icon="banknotes"
          label="Disbursed (all time)"
          value={d ? formatKESShort(d.portfolio.total_disbursed_all_time) : "…"}
          sub={d ? <>{formatKESShort(d.flows.disbursed_amount)} in this period</> : null}
        />
        <KpiTile
          loading={loading}
          tone="neutral"
          icon="wallet"
          label="Repaid (all time)"
          value={d ? formatKESShort(d.portfolio.total_repaid_all_time) : "…"}
          sub={d ? <>{formatKESShort(d.flows.collected_amount)} in this period</> : null}
          to="/branch-manager/loans?stage=repaid"
        />
      </div>

      {d ? (
        <>
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card>
              <SectionLabel>What's owed</SectionLabel>
              <dl className="space-y-2 text-sm">
                {[
                  ["Principal", d.portfolio.outstanding_principal],
                  ["Interest", d.portfolio.outstanding_interest],
                  ["Penalties", d.portfolio.outstanding_penalties],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between">
                    <dt className="text-slate-600 dark:text-slate-300">{label}</dt>
                    <dd className="font-semibold tabular-nums text-slate-900 dark:text-slate-50">{formatKESShort(value)}</dd>
                  </div>
                ))}
              </dl>
              <div className="mt-4 space-y-4">
                <RateMeter
                  label="Loan book repaid"
                  pct={d.portfolio.repayment_progress_pct}
                  numerator={d.portfolio.total_repaid_all_time}
                  denominator={addDecimal(d.portfolio.total_repaid_all_time, d.portfolio.outstanding_total)}
                />
                <RateMeter
                  label="Collection rate (this period)"
                  pct={d.flows.collection_rate_pct}
                  numerator={d.flows.paid_against_due}
                  denominator={d.flows.due_amount}
                  tone={Number(d.flows.collection_rate_pct) >= 90 ? "success" : Number(d.flows.collection_rate_pct) >= 70 ? "warning" : "danger"}
                />
              </div>
            </Card>
            <Card>
              <SectionLabel>Loans by status (all time)</SectionLabel>
              <PipelineList stages={d.pipeline_all_time} linkBase="/branch-manager/loans" />
            </Card>
            <Card>
              <SectionLabel>Arrears aging</SectionLabel>
              <AgingChart data={d} />
            </Card>
          </div>
          <Card className="mt-4">
            <SectionLabel>Disbursed vs collected</SectionLabel>
            <FlowChart data={d} />
          </Card>
        </>
      ) : null}
    </AppShell>
  );
}
