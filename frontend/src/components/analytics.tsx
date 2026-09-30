/** Shared staff-dashboard building blocks (credit officer, finance, and any
 * later role) over GET /analytics/*. Every figure shown is a server-computed
 * Decimal string (CLAUDE.md §23: the frontend never computes real money);
 * charts convert to numbers only to size the marks.
 *
 * Chart palette (validated with the dataviz CVD checker, light + dark):
 * disbursed = indigo #6366f1, collected = emerald #059669. Aging uses one
 * sequential rose ramp (magnitude of lateness), "current" in slate.
 */
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiRequest } from "../api/client";
import { safeHex, useBranding } from "../branding";
import {
  INSTALLMENT_META,
  STAGE_META,
  chartNumber,
  formatDate,
  formatDateTime,
  formatKES,
  formatKESShort,
  type DashboardResponse,
  type DueListItem,
  type StageCount,
  type TimelineResponse,
} from "../schemas/analytics";
import { DataTable } from "./DataTable";
import { Icon, type IconName } from "./icons";
import { Skeleton } from "./Skeleton";
import { Badge, Banner, Card, EmptyState, SectionLabel } from "./ui";

export const CHART_COLORS = {
  disbursed: "#6366f1",
  collected: "#059669",
  due: "#94a3b8",
};
const AGING_COLORS: Record<string, string> = {
  current: "#94a3b8",
  "1-7": "#fda4af",
  "8-30": "#fb7185",
  "31-60": "#f43f5e",
  "61-90": "#e11d48",
  "90+": "#9f1239",
};
const AXIS_TICK = { fill: "#94a3b8", fontSize: 11 };
const GRID_STROKE = "rgba(148, 163, 184, 0.18)";

// --------------------------------------------------------------------------
// Date range (URL-backed so a refresh or shared link keeps it)
// --------------------------------------------------------------------------

type Preset = "today" | "7d" | "30d" | "mtd" | "ytd" | "custom";

const PRESETS: { value: Exclude<Preset, "custom">; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "mtd", label: "This month" },
  { value: "ytd", label: "This year" },
];

function isoLocal(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function presetRange(preset: Exclude<Preset, "custom">): { start: string; end: string } {
  const today = new Date();
  const end = isoLocal(today);
  const back = (days: number) => {
    const d = new Date(today);
    d.setDate(d.getDate() - days);
    return isoLocal(d);
  };
  switch (preset) {
    case "today":
      return { start: end, end };
    case "7d":
      return { start: back(6), end };
    case "30d":
      return { start: back(29), end };
    case "ytd":
      return { start: `${today.getFullYear()}-01-01`, end };
    case "mtd":
    default:
      return { start: isoLocal(new Date(today.getFullYear(), today.getMonth(), 1)), end };
  }
}

/** Default: month to date — long enough to show a trend, short enough to
 * match how collections targets are usually tracked. */
export function useDateRange() {
  const [params, setParams] = useSearchParams();
  const preset = (params.get("range") as Preset | null) ?? "mtd";
  const range =
    preset === "custom" && params.get("from") && params.get("to")
      ? { start: params.get("from")!, end: params.get("to")! }
      : presetRange(preset === "custom" ? "mtd" : preset);

  function setPreset(next: Exclude<Preset, "custom">) {
    const p = new URLSearchParams(params);
    p.set("range", next);
    p.delete("from");
    p.delete("to");
    setParams(p, { replace: true });
  }
  function setCustom(start: string, end: string) {
    const p = new URLSearchParams(params);
    p.set("range", "custom");
    p.set("from", start);
    p.set("to", end);
    setParams(p, { replace: true });
  }
  return { preset, ...range, setPreset, setCustom };
}

export function DateRangeBar({ range }: { range: ReturnType<typeof useDateRange> }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="inline-flex flex-wrap rounded-lg border border-slate-200 bg-white p-0.5 dark:border-slate-700 dark:bg-slate-900">
        {PRESETS.map((p) => (
          <button
            key={p.value}
            type="button"
            onClick={() => range.setPreset(p.value)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              range.preset === p.value
                ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
        <input
          type="date"
          aria-label="From date"
          value={range.start}
          max={range.end}
          onChange={(e) => e.target.value && range.setCustom(e.target.value, range.end)}
          className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
        />
        <span>to</span>
        <input
          type="date"
          aria-label="To date"
          value={range.end}
          min={range.start}
          onChange={(e) => e.target.value && range.setCustom(range.start, e.target.value)}
          className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
        />
      </div>
    </div>
  );
}

export function useDashboard(range: { start: string; end: string }, opts: { mine?: boolean } = {}) {
  const mine = opts.mine ?? false;
  return useQuery({
    queryKey: ["analytics", "dashboard", range.start, range.end, mine],
    queryFn: () =>
      apiRequest<DashboardResponse>(
        `/analytics/dashboard?start=${range.start}&end=${range.end}${mine ? "&mine=true" : ""}`,
      ),
  });
}

// --------------------------------------------------------------------------
// KPI tiles
// --------------------------------------------------------------------------

type KpiTone = "brand" | "amber" | "danger" | "success" | "neutral";

const KPI_SURFACES: Record<KpiTone, string> = {
  brand: "bg-gradient-to-br from-violet-600 via-indigo-600 to-blue-600 text-white shadow-lg shadow-indigo-600/20",
  amber: "bg-gradient-to-br from-amber-400 to-orange-500 text-slate-950 shadow-lg shadow-amber-500/20",
  danger: "bg-gradient-to-br from-rose-600 to-red-600 text-white shadow-lg shadow-rose-600/20",
  success: "bg-gradient-to-br from-emerald-600 to-teal-600 text-white shadow-lg shadow-emerald-600/20",
  neutral:
    "border border-slate-200/80 bg-white text-slate-900 shadow-sm dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-50",
};
const KPI_MUTED: Record<KpiTone, string> = {
  brand: "text-white/80",
  amber: "text-slate-900/75",
  danger: "text-white/80",
  success: "text-white/80",
  neutral: "text-slate-500 dark:text-slate-400",
};

/** A clickable headline number. `to` makes the whole tile a link to the
 * drill-down list it summarizes. */
export function KpiTile({
  label,
  value,
  sub,
  tone = "neutral",
  icon,
  to,
  loading,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: KpiTone;
  icon?: IconName;
  to?: string;
  loading?: boolean;
}) {
  const branding = useBranding();
  const primary = tone === "brand" ? safeHex(branding.primaryColor) : undefined;
  const accent = tone === "brand" ? (safeHex(branding.accentColor) ?? primary) : undefined;
  const style = primary ? { backgroundImage: `linear-gradient(to bottom right, ${primary}, ${accent})` } : undefined;

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-200/80 bg-white p-5 dark:border-slate-800 dark:bg-slate-900/70">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="mt-3 h-8 w-32" />
        <Skeleton className="mt-3 h-3 w-40" />
      </div>
    );
  }

  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className={`text-xs font-semibold uppercase tracking-wider ${KPI_MUTED[tone]}`}>{label}</p>
        {icon ? <Icon name={icon} className={`h-5 w-5 shrink-0 ${KPI_MUTED[tone]}`} /> : null}
      </div>
      <p className="mt-2 text-3xl font-black tracking-tight tabular-nums">{value}</p>
      {sub ? <div className={`mt-1.5 text-xs ${KPI_MUTED[tone]}`}>{sub}</div> : null}
      {to ? <p className={`mt-3 text-xs font-semibold ${KPI_MUTED[tone]}`}>View details →</p> : null}
    </>
  );
  const className = `block h-full rounded-2xl p-5 transition-all duration-150 ${KPI_SURFACES[tone]} ${
    to ? "hover:-translate-y-0.5 hover:shadow-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500" : ""
  }`;
  return to ? (
    <Link to={to} className={className} style={style}>
      {body}
    </Link>
  ) : (
    <div className={className} style={style}>
      {body}
    </div>
  );
}

/** One quantity against a target, e.g. collection rate. Prints both numbers
 * and the percentage — never relies on bar length alone. */
export function RateMeter({
  label,
  pct,
  numerator,
  denominator,
  tone = "brand",
  hint,
}: {
  label: string;
  pct: string;
  numerator: string;
  denominator: string;
  tone?: "brand" | "success" | "danger" | "warning";
  hint?: string;
}) {
  const width = Math.max(0, Math.min(100, chartNumber(pct)));
  const bar = { brand: "bg-indigo-500", success: "bg-emerald-600", danger: "bg-rose-500", warning: "bg-amber-500" }[tone];
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{label}</span>
        <span className="text-lg font-bold tabular-nums text-slate-900 dark:text-slate-50">{pct}%</span>
      </div>
      <div className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        <div className={`h-full rounded-full transition-[width] duration-700 ${bar}`} style={{ width: `${width}%` }} />
      </div>
      <p className="mt-1 text-xs tabular-nums text-slate-500 dark:text-slate-400">
        {formatKESShort(numerator)} of {formatKESShort(denominator)}
        {hint ? ` · ${hint}` : ""}
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------
// Charts
// --------------------------------------------------------------------------

function ChartTooltip({
  active,
  payload,
  label,
  labelFormatter,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string; payload: Record<string, string> ; dataKey: string }[];
  label?: string;
  labelFormatter?: (label: string) => string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900">
      <p className="mb-1 font-semibold text-slate-900 dark:text-slate-50">{labelFormatter && label ? labelFormatter(label) : label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
          <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: p.color }} />
          {p.name}: <span className="font-semibold tabular-nums text-slate-900 dark:text-slate-50">{formatKES(p.payload[`${p.dataKey}_raw`])}</span>
        </p>
      ))}
    </div>
  );
}

function periodLabel(period: string, granularity: "day" | "month"): string {
  const d = new Date(`${period}T00:00:00`);
  return granularity === "day"
    ? d.toLocaleDateString(undefined, { day: "numeric", month: "short" })
    : d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
}

function compactAxis(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}K`;
  return String(value);
}

/** Disbursed vs collected per period — two series of the same unit on one
 * axis (never a dual axis). */
export function FlowChart({ data }: { data: DashboardResponse }) {
  const rows = useMemo(
    () =>
      data.series.map((p) => ({
        period: p.period,
        disbursed: chartNumber(p.disbursed),
        collected: chartNumber(p.collected),
        disbursed_raw: p.disbursed,
        collected_raw: p.collected,
      })),
    [data.series],
  );
  const empty = rows.every((r) => r.disbursed === 0 && r.collected === 0);
  if (empty) return <EmptyState>No money moved in this period.</EmptyState>;
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} barGap={2} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID_STROKE} />
          <XAxis
            dataKey="period"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: string) => periodLabel(v, data.granularity)}
            minTickGap={16}
          />
          <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={compactAxis} width={44} />
          <Tooltip
            cursor={{ fill: "rgba(148,163,184,0.12)" }}
            content={<ChartTooltip labelFormatter={(l) => periodLabel(l, data.granularity)} />}
          />
          <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="disbursed" name="Disbursed" fill={CHART_COLORS.disbursed} radius={[4, 4, 0, 0]} maxBarSize={28} />
          <Bar dataKey="collected" name="Collected" fill={CHART_COLORS.collected} radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

const AGING_LABEL: Record<string, string> = {
  current: "Current",
  "1-7": "1–7 days",
  "8-30": "8–30 days",
  "31-60": "31–60 days",
  "61-90": "61–90 days",
  "90+": "90+ days",
};

/** Outstanding balance by days past due — one sequential hue, darker = later. */
export function AgingChart({ data }: { data: DashboardResponse }) {
  const rows = data.aging.map((a) => ({
    bucket: a.bucket,
    label: AGING_LABEL[a.bucket] ?? a.bucket,
    amount: chartNumber(a.amount),
    amount_raw: a.amount,
    count: a.count,
  }));
  if (rows.every((r) => r.count === 0)) return <EmptyState>No outstanding loans.</EmptyState>;
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke={GRID_STROKE} />
          <XAxis type="number" tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={compactAxis} />
          <YAxis type="category" dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} width={78} />
          <Tooltip
            cursor={{ fill: "rgba(148,163,184,0.12)" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload as (typeof rows)[number];
              return (
                <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900">
                  <p className="font-semibold text-slate-900 dark:text-slate-50">{row.label}</p>
                  <p className="text-slate-600 dark:text-slate-300">
                    {row.count} loan{row.count === 1 ? "" : "s"} · {formatKES(row.amount_raw)}
                  </p>
                </div>
              );
            }}
          />
          <Bar dataKey="amount" name="Outstanding" radius={[0, 4, 4, 0]} maxBarSize={22}>
            {rows.map((r) => (
              <Cell key={r.bucket} fill={AGING_COLORS[r.bucket] ?? "#94a3b8"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Money falling due over the next 7 days — a single series, so no legend. */
export function NextDaysChart({ data }: { data: DashboardResponse }) {
  const rows = data.due.next_7_days.map((d, i) => ({
    date: d.date,
    label: i === 0 ? "Today" : new Date(`${d.date}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric" }),
    amount: chartNumber(d.amount),
    amount_raw: d.amount,
    count: d.count,
  }));
  if (rows.every((r) => r.count === 0)) return <EmptyState>Nothing falls due in the next 7 days.</EmptyState>;
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID_STROKE} />
          <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} />
          <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={compactAxis} width={44} />
          <Tooltip
            cursor={{ fill: "rgba(148,163,184,0.12)" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload as (typeof rows)[number];
              return (
                <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900">
                  <p className="font-semibold text-slate-900 dark:text-slate-50">{formatDate(row.date)}</p>
                  <p className="text-slate-600 dark:text-slate-300">
                    {row.count} instalment{row.count === 1 ? "" : "s"} · {formatKES(row.amount_raw)}
                  </p>
                </div>
              );
            }}
          />
          <Bar dataKey="amount" name="Due" fill={CHART_COLORS.disbursed} radius={[4, 4, 0, 0]} maxBarSize={32} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

const PIPELINE_BAR: Record<string, string> = {
  warning: "bg-amber-500",
  info: "bg-blue-500",
  brand: "bg-indigo-500",
  danger: "bg-rose-500",
  success: "bg-emerald-600",
  neutral: "bg-slate-400",
};

/** Applications by lifecycle stage. Each row links to that stage's list. */
export function PipelineList({
  stages,
  linkBase,
  labels,
}: {
  stages: StageCount[];
  linkBase?: string;
  /** Per-role wording, e.g. finance reads "in review" as "Pending". */
  labels?: Partial<Record<StageCount["stage"], string>>;
}) {
  const max = Math.max(1, ...stages.map((s) => s.count));
  const total = stages.reduce((n, s) => n + s.count, 0);
  if (total === 0) return <EmptyState>No applications in this period.</EmptyState>;
  return (
    <ul className="space-y-2.5">
      {stages.map((s) => {
        const meta = STAGE_META[s.stage];
        const row = (
          <>
            <div className="mb-1 flex items-center justify-between gap-2 text-xs">
              <span className="font-medium text-slate-700 dark:text-slate-200">{labels?.[s.stage] ?? meta.label}</span>
              <span className="tabular-nums text-slate-500 dark:text-slate-400">
                <span className="font-semibold text-slate-900 dark:text-slate-50">{s.count}</span> · {formatKESShort(s.amount)}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div
                className={`h-full rounded-full transition-[width] duration-500 ${PIPELINE_BAR[meta.tone]}`}
                style={{ width: `${s.count === 0 ? 0 : Math.max(3, Math.round((s.count / max) * 100))}%` }}
              />
            </div>
          </>
        );
        return (
          <li key={s.stage}>
            {linkBase ? (
              <Link to={`${linkBase}?stage=${s.stage}`} className="block rounded-md p-1 -m-1 hover:bg-slate-50 dark:hover:bg-slate-800/60">
                {row}
              </Link>
            ) : (
              row
            )}
          </li>
        );
      })}
    </ul>
  );
}

// --------------------------------------------------------------------------
// Due list
// --------------------------------------------------------------------------

export function DueListTable({ items, onOpen }: { items: DueListItem[]; onOpen: (applicationId: number) => void }) {
  return (
    <DataTable
      columns={[
        { key: "customer", header: "Customer", sortable: true, accessor: (r: DueListItem) => r.customer_full_name },
        {
          key: "due_date",
          header: "Due date",
          sortable: true,
          accessor: (r) => r.due_date,
          render: (r) => formatDate(r.due_date),
        },
        {
          key: "amount",
          header: "Amount due",
          sortable: true,
          accessor: (r) => chartNumber(r.amount_remaining),
          render: (r) => <span className="tabular-nums">{formatKES(r.amount_remaining)}</span>,
        },
        {
          key: "state",
          header: "Status",
          accessor: (r) => r.days_past_due,
          render: (r) => (
            <Badge tone={INSTALLMENT_META[r.state].tone}>
              {r.state === "overdue" ? `Overdue · ${r.days_past_due}d` : INSTALLMENT_META[r.state].label}
            </Badge>
          ),
        },
      ]}
      data={items}
      getRowId={(r) => `${r.loan_id}-${r.installment_number}`}
      emptyMessage="No instalments overdue or due in the next 7 days."
      pageSize={8}
      onRowClick={(r) => onOpen(r.application_id)}
    />
  );
}

// --------------------------------------------------------------------------
// Timeline (movement history of one loan)
// --------------------------------------------------------------------------

const DOT_TONE: Record<string, string> = {
  success: "bg-emerald-500",
  danger: "bg-rose-500",
  warning: "bg-amber-500",
  info: "bg-blue-500",
  brand: "bg-indigo-500",
  neutral: "bg-slate-400",
};

function Figure({ label, value, emphasis }: { label: string; value: ReactNode; emphasis?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className={`tabular-nums ${emphasis ? "text-base font-bold" : "text-sm font-semibold"} text-slate-900 dark:text-slate-50`}>
        {value}
      </dd>
    </div>
  );
}

export function LoanTimeline({ applicationId }: { applicationId: number }) {
  const query = useQuery({
    queryKey: ["analytics", "timeline", applicationId],
    queryFn: () => apiRequest<TimelineResponse>(`/analytics/applications/${applicationId}/timeline`),
  });

  if (query.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (query.isError || !query.data) return <Banner kind="error">Couldn't load this loan's history.</Banner>;

  const t = query.data;
  const stage = STAGE_META[t.stage];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge tone={stage.tone}>{stage.label}</Badge>
        <span className="text-slate-600 dark:text-slate-300">{t.loan_product_name}</span>
        {t.customer_number ? <span className="text-slate-400">· {t.customer_number}</span> : null}
      </div>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <Figure label="Phone" value={t.customer_phone ?? "—"} />
        <Figure label="Branch" value={t.branch_name ?? "—"} />
        <Figure label="Prepared by" value={t.prepared_by_name ?? "Self-service"} />
        <Figure label="Applied" value={formatDateTime(t.created_at)} />
      </dl>

      {t.loan ? (
        <Card>
          <SectionLabel>Loan position</SectionLabel>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Figure label="Principal" value={formatKES(t.loan.principal)} />
            <Figure label="Interest" value={formatKES(t.loan.interest)} />
            <Figure label="Penalties" value={formatKES(t.loan.penalties)} />
            <Figure label="Total owed" value={formatKES(t.loan.total_owed)} />
            <Figure label="Repaid" value={formatKES(t.loan.repaid)} />
            <Figure label="Outstanding" value={formatKES(t.loan.outstanding_balance)} emphasis />
            <Figure label="Disbursed" value={formatDateTime(t.loan.disbursed_at)} />
            <Figure
              label="Next due"
              value={
                t.loan.next_due_date ? (
                  <span className={t.loan.days_past_due > 0 ? "text-rose-600 dark:text-rose-400" : ""}>
                    {formatDate(t.loan.next_due_date)}
                    {t.loan.days_past_due > 0 ? ` (${t.loan.days_past_due}d late)` : ""}
                  </span>
                ) : (
                  "—"
                )
              }
            />
          </dl>
          <div className="mt-4">
            <RateMeter
              label="Repayment progress"
              pct={t.loan.progress_pct}
              numerator={t.loan.repaid}
              denominator={t.loan.total_owed}
              tone={t.loan.days_past_due > 0 ? "danger" : "success"}
            />
          </div>
        </Card>
      ) : null}

      <div>
        <SectionLabel>Movement history</SectionLabel>
        {t.events.length === 0 ? (
          <EmptyState>No recorded movements yet.</EmptyState>
        ) : (
          <ol className="relative ml-2 border-l border-slate-200 dark:border-slate-700">
            {t.events.map((e, i) => (
              <li key={`${e.kind}-${i}`} className="relative mb-4 ml-5 last:mb-0">
                <span
                  className={`absolute -left-[1.6rem] top-1 h-3 w-3 rounded-full ring-4 ring-white dark:ring-slate-950 ${DOT_TONE[e.tone] ?? DOT_TONE.neutral}`}
                />
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-50">{e.title}</p>
                  {e.amount ? <p className="text-sm font-semibold tabular-nums text-slate-700 dark:text-slate-200">{formatKES(e.amount)}</p> : null}
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {formatDateTime(e.at)}
                  {e.actor_name ? ` · ${e.actor_name}` : ""}
                </p>
                {e.detail ? <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-300">“{e.detail}”</p> : null}
              </li>
            ))}
          </ol>
        )}
      </div>

      {t.schedule.length > 0 ? (
        <div>
          <SectionLabel>Repayment schedule</SectionLabel>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 dark:text-slate-400">
                  <th className="py-1.5 pr-3 font-medium">#</th>
                  <th className="py-1.5 pr-3 font-medium">Due date</th>
                  <th className="py-1.5 pr-3 font-medium">Due</th>
                  <th className="py-1.5 pr-3 font-medium">Paid</th>
                  <th className="py-1.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {t.schedule.map((s) => (
                  <tr key={s.installment_number} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1.5 pr-3 tabular-nums">{s.installment_number}</td>
                    <td className="py-1.5 pr-3">{formatDate(s.due_date)}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{formatKES(s.amount_due)}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{formatKES(s.amount_paid)}</td>
                    <td className="py-1.5">
                      <Badge tone={INSTALLMENT_META[s.state].tone}>
                        {s.state === "overdue" ? `Overdue · ${s.days_past_due}d` : INSTALLMENT_META[s.state].label}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
