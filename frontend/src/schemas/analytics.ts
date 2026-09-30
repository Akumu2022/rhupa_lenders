// Mirrors backend app/schemas/analytics.py. Money fields are Decimal strings
// (CLAUDE.md rule #13) — they are formatted for display as strings, never
// parsed into floats for arithmetic. Charts are the one place a number is
// needed (a bar's height), and only for drawing: every figure a person reads
// comes straight from the server string.

export type Stage =
  | "in_review"
  | "awaiting_disbursement"
  | "active"
  | "overdue"
  | "defaulted"
  | "repaid"
  | "rejected";

export type Tone = "success" | "danger" | "warning" | "info" | "neutral" | "brand";

export const STAGE_META: Record<Stage, { label: string; tone: Tone }> = {
  in_review: { label: "In review", tone: "warning" },
  awaiting_disbursement: { label: "Awaiting disbursement", tone: "info" },
  active: { label: "Active", tone: "brand" },
  overdue: { label: "Overdue", tone: "danger" },
  defaulted: { label: "Defaulted", tone: "danger" },
  repaid: { label: "Repaid", tone: "success" },
  rejected: { label: "Rejected", tone: "neutral" },
};

/** "Sorted" = approved and moved on (everything past a yes). */
export const SORTED_STAGES: Stage[] = ["awaiting_disbursement", "active", "overdue", "defaulted", "repaid"];

export interface StageCount {
  stage: Stage;
  count: number;
  amount: string;
}

export interface DashboardResponse {
  start: string;
  end: string;
  as_of: string;
  scope: "mine" | "branch" | "company" | "unassigned";
  queues: {
    in_review_count: number;
    in_review_amount: string;
    awaiting_disbursement_count: number;
    awaiting_disbursement_amount: string;
  };
  pipeline: StageCount[];
  pipeline_all_time: StageCount[];
  flows: {
    disbursed_count: number;
    disbursed_amount: string;
    collected_count: number;
    collected_amount: string;
    penalties_charged: string;
    due_amount: string;
    paid_against_due: string;
    collection_rate_pct: string;
  };
  portfolio: {
    active_loans: number;
    overdue_loans: number;
    defaulted_loans: number;
    repaid_loans: number;
    active_borrowers: number;
    total_disbursed_all_time: string;
    total_repaid_all_time: string;
    outstanding_principal: string;
    outstanding_interest: string;
    outstanding_penalties: string;
    outstanding_total: string;
    arrears_amount: string;
    repayment_progress_pct: string;
    par_pct: string;
  };
  due: {
    today_count: number;
    today_amount: string;
    today_collected: string;
    today_paid: number;
    today_partial: number;
    today_unpaid: number;
    overdue_installments: number;
    next_7_days: { date: string; count: number; amount: string }[];
    next_30_days_amount: string;
    next_30_days_count: number;
  };
  aging: { bucket: string; count: number; amount: string }[];
  granularity: "day" | "month";
  series: { period: string; disbursed: string; collected: string; due: string }[];
  due_list: DueListItem[];
}

export interface DueListItem {
  application_id: number;
  loan_id: number;
  customer_full_name: string;
  installment_number: number;
  due_date: string;
  amount_remaining: string;
  days_past_due: number;
  state: InstallmentState;
}

export type InstallmentState = "paid" | "partial" | "overdue" | "due_today" | "upcoming";

export const INSTALLMENT_META: Record<InstallmentState, { label: string; tone: Tone }> = {
  paid: { label: "Paid", tone: "success" },
  partial: { label: "Partially paid", tone: "warning" },
  overdue: { label: "Overdue", tone: "danger" },
  due_today: { label: "Due today", tone: "warning" },
  upcoming: { label: "Upcoming", tone: "neutral" },
};

export interface ApplicationListItem {
  id: number;
  customer_id: number;
  customer_full_name: string;
  customer_email: string;
  loan_product_name: string;
  amount_requested: string;
  status: string;
  loan_id: number | null;
  loan_status: string | null;
  stage: Stage;
  prepared_by_name: string | null;
  created_at: string;
  reviewed_at: string | null;
  review_notes: string | null;
  principal: string | null;
  outstanding_balance: string | null;
  disbursed_at: string | null;
  next_due_date: string | null;
  days_past_due: number;
}

export interface TimelineEvent {
  at: string;
  kind: string;
  title: string;
  tone: Tone;
  actor_name: string | null;
  detail: string | null;
  amount: string | null;
}

export interface ScheduleItem {
  installment_number: number;
  due_date: string;
  amount_due: string;
  amount_paid: string;
  principal_component: string;
  interest_component: string;
  state: InstallmentState;
  days_past_due: number;
}

export interface TimelineResponse {
  application_id: number;
  customer_full_name: string;
  customer_email: string;
  customer_phone: string | null;
  customer_number: string | null;
  loan_product_name: string;
  branch_name: string | null;
  amount_requested: string;
  stage: Stage;
  prepared_by_name: string | null;
  created_at: string;
  loan: {
    loan_id: number;
    status: string;
    principal: string;
    interest: string;
    penalties: string;
    total_owed: string;
    repaid: string;
    outstanding_balance: string;
    outstanding_principal: string;
    outstanding_interest: string;
    outstanding_penalties: string;
    disbursed_at: string | null;
    next_due_date: string | null;
    days_past_due: number;
    progress_pct: string;
  } | null;
  events: TimelineEvent[];
  schedule: ScheduleItem[];
}

/** "12345.5" -> "KES 12,345.50" — pure string formatting, no float. */
export function formatKES(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const negative = value.startsWith("-");
  const raw = negative ? value.slice(1) : value;
  const [intPart, fracPart = ""] = raw.split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${negative ? "-" : ""}KES ${grouped}.${fracPart.padEnd(2, "0").slice(0, 2)}`;
}

/** Whole-shilling short form for tight tiles: "KES 1,234,567". */
export function formatKESShort(value: string | null | undefined): string {
  const full = formatKES(value);
  return full === "—" ? full : full.replace(/\.\d{2}$/, "");
}

/** Chart-geometry only (bar heights) — never shown as a figure. */
export function chartNumber(value: string): number {
  return Number(value);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  // Plain YYYY-MM-DD from the server is a calendar date — parse it as local,
  // not UTC midnight (which can shift the day in some timezones).
  const d = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Exact decimal-string addition via integer cents (BigInt) — display
 * totals of server figures without ever going through a float. */
export function addDecimal(a: string, b: string): string {
  const cents = toCents(a) + toCents(b);
  return fromCents(cents);
}

function toCents(value: string): bigint {
  const negative = value.startsWith("-");
  const [i, f = ""] = (negative ? value.slice(1) : value).split(".");
  const cents = BigInt(i || "0") * 100n + BigInt((f + "00").slice(0, 2));
  return negative ? -cents : cents;
}

function fromCents(cents: bigint): string {
  const negative = cents < 0n;
  const abs = negative ? -cents : cents;
  return `${negative ? "-" : ""}${abs / 100n}.${String(abs % 100n).padStart(2, "0")}`;
}

/** Percentage of two decimal strings, to 2 places, via integer math. */
export function pctString(numerator: string, denominator: string): string {
  const d = toCents(denominator);
  if (d <= 0n) return "0.00";
  const basisPoints = (toCents(numerator) * 10000n + d / 2n) / d;
  return `${basisPoints / 100n}.${String(basisPoints % 100n).padStart(2, "0")}`;
}

export function sumDecimal(values: string[]): string {
  return fromCents(values.reduce((total, v) => total + toCents(v), 0n));
}
