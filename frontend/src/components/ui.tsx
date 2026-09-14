import { useEffect, useId, useRef, useState } from "react";
import type { CSSProperties, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { Link } from "react-router-dom";
import { safeHex, useBranding } from "../branding";
import { Icon, type IconName } from "./icons";
import { Skeleton } from "./Skeleton";

/** Decorative, ambient gradient blobs behind a hero section — the "second
 * accent hue" + visual energy a 2026 consumer-fintech dashboard (Revolut/
 * Chime/Cash App) carries that a purely flat Stripe/Mercury-style surface
 * doesn't. Always `aria-hidden`, `pointer-events-none`, and clipped by an
 * `overflow-hidden` ancestor (AppShell) so it can never cause horizontal
 * scroll or intercept clicks/keyboard focus. Opacity is low enough that it
 * never competes with foreground text contrast. */
export function AuroraBackground() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[32rem] overflow-hidden">
      <div className="animate-aurora absolute -left-24 -top-32 h-96 w-96 rounded-full bg-gradient-to-br from-violet-500 to-indigo-500 opacity-[0.16] blur-3xl dark:opacity-[0.22]" />
      <div className="animate-aurora absolute -right-16 top-0 h-[28rem] w-[28rem] rounded-full bg-gradient-to-br from-blue-400 to-cyan-400 opacity-[0.14] blur-3xl dark:opacity-20 [animation-delay:-9s]" />
      <div className="animate-aurora absolute left-1/3 top-40 h-72 w-72 rounded-full bg-gradient-to-br from-emerald-400 to-teal-400 opacity-[0.08] blur-3xl dark:opacity-[0.12] [animation-delay:-15s]" />
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl border border-slate-200/80 bg-white p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.08)] dark:border-slate-800 dark:bg-slate-900/70 dark:shadow-[0_1px_2px_rgba(0,0,0,0.2),0_8px_24px_-12px_rgba(0,0,0,0.4)] dark:backdrop-blur-sm ${className}`}
    >
      {children}
    </div>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
      {children}
    </h2>
  );
}

export function Field({ label, children, error }: { label: string; children: ReactNode; error?: string }) {
  return (
    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
      {label}
      <div className="mt-1.5">{children}</div>
      {error ? <p className="mt-1 text-xs font-normal text-rose-600 dark:text-rose-400">{error}</p> : null}
    </label>
  );
}

const inputBase =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition-colors placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-indigo-400";

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputBase} ${props.className ?? ""}`} />;
}

export function Select({
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <select {...props} className={`${inputBase} ${props.className ?? ""}`}>
      {children}
    </select>
  );
}

export function Button({
  variant = "primary",
  className = "",
  style,
  disabled,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles: Record<string, string> = {
    primary:
      "bg-gradient-to-r from-violet-600 to-blue-600 text-white shadow-md shadow-violet-600/25 hover:shadow-lg hover:shadow-violet-600/35 hover:from-violet-500 hover:to-blue-500 disabled:from-slate-300 disabled:to-slate-300 disabled:shadow-none dark:disabled:from-slate-700 dark:disabled:to-slate-700",
    secondary:
      "bg-white text-slate-700 border border-slate-300 shadow-sm hover:bg-slate-50 hover:border-slate-400 disabled:text-slate-400 disabled:hover:bg-white dark:bg-slate-900 dark:text-slate-300 dark:border-slate-700 dark:hover:bg-slate-800 dark:hover:border-slate-600 dark:disabled:text-slate-600 dark:disabled:hover:bg-slate-900",
    danger:
      "bg-rose-600 text-white shadow-sm shadow-rose-600/20 hover:bg-rose-500 disabled:bg-rose-300 disabled:shadow-none dark:disabled:bg-rose-900",
  };

  // CLAUDE.md §21: the primary action color is the one accent a tenant's
  // brand actually shows up in throughout the app — everything else (layout,
  // spacing, other components) stays platform-controlled. Disabled state
  // keeps the neutral Tailwind gradient so "can't submit" always reads the
  // same regardless of brand color.
  const branding = useBranding();
  const primary = !disabled ? safeHex(branding.primaryColor) : undefined;
  const brandStyle: CSSProperties | undefined =
    variant === "primary" && primary
      ? { backgroundImage: `linear-gradient(to right, ${primary}, ${safeHex(branding.accentColor) ?? primary})` }
      : undefined;

  return (
    <button
      {...props}
      disabled={disabled}
      style={{ ...brandStyle, ...style }}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold transition-all duration-150 active:scale-[0.98] disabled:cursor-not-allowed disabled:active:scale-100 ${styles[variant]} ${className}`}
    />
  );
}

const BANNER_STYLES: Record<string, { wrap: string; icon: ReactNode }> = {
  error: {
    wrap: "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4 shrink-0 text-rose-500 dark:text-rose-400">
        <path
          fillRule="evenodd"
          d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.63-1.516 2.63H3.72c-1.347 0-2.189-1.463-1.516-2.63L8.485 2.495ZM10 6a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 10 6Zm0 8a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
          clipRule="evenodd"
        />
      </svg>
    ),
  },
  success: {
    wrap: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-300",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4 shrink-0 text-emerald-500 dark:text-emerald-400">
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm3.857-9.809a.75.75 0 0 0-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 1 0-1.06 1.061l2.5 2.5a.75.75 0 0 0 1.137-.089l4-5.5Z"
          clipRule="evenodd"
        />
      </svg>
    ),
  },
  info: {
    wrap: "border-indigo-200 bg-indigo-50 text-indigo-800 dark:border-indigo-900/60 dark:bg-indigo-950/40 dark:text-indigo-300",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4 shrink-0 text-indigo-500 dark:text-indigo-400">
        <path
          fillRule="evenodd"
          d="M18 10A8 8 0 1 1 2 10a8 8 0 0 1 16 0ZM9 9a1 1 0 0 1 1-1h.01a1 1 0 1 1 0 2H10a1 1 0 0 1-1-1Zm0 3a1 1 0 1 0 0 2h1a1 1 0 1 0 0-2h-1Z"
          clipRule="evenodd"
        />
      </svg>
    ),
  },
};

export function Banner({ kind = "error", children }: { kind?: "error" | "success" | "info"; children: ReactNode }) {
  const style = BANNER_STYLES[kind];
  return (
    <div className={`flex items-start gap-2 rounded-lg border px-3.5 py-2.5 text-sm ${style.wrap}`}>
      {style.icon}
      <span>{children}</span>
    </div>
  );
}

const BADGE_TONES: Record<string, string> = {
  success: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  danger: "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
  warning: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  info: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  neutral: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  brand: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
};

export function Badge({
  tone = "neutral",
  children,
  className = "",
  style,
}: {
  tone?: "success" | "danger" | "warning" | "info" | "neutral" | "brand";
  children: ReactNode;
  className?: string;
  /** Escape hatch for cosmetic per-tenant branding overrides (CLAUDE.md §21)
   * — never used for anything the platform's own tone system should decide. */
  style?: CSSProperties;
}) {
  // tone="brand" is the one tone that means "this tenant's identity", not a
  // fixed platform state (unlike success/danger/warning/info/neutral, which
  // CLAUDE.md §18 pins to one meaning everywhere and must never shift per
  // tenant) — so it's the only tone that picks up the company's own color.
  // An explicit `style` prop (a caller with its own status-aware logic)
  // always wins over this default.
  const branding = useBranding();
  const primary = tone === "brand" ? safeHex(branding.primaryColor) : undefined;
  const autoStyle: CSSProperties | undefined = primary ? { backgroundColor: `${primary}1a`, color: primary } : undefined;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${BADGE_TONES[tone]} ${className}`}
      style={style ?? autoStyle}
    >
      {children}
    </span>
  );
}

/** §20 motion: KPI numbers count up to their new value instead of popping —
 * subtle, not novelty. Only for genuinely numeric values; a formatted string
 * like "KES 5,000" or a placeholder like "…" renders as plain text (parsing
 * currency strings to animate them isn't worth the risk of showing a wrong
 * number mid-animation in a financial app). Skips the animation entirely
 * under prefers-reduced-motion or on the number's first appearance.
 */
function AnimatedNumber({ value }: { value: number }) {
  const [display, setDisplay] = useState(value);
  const prevValue = useRef<number | null>(null);

  useEffect(() => {
    const from = prevValue.current;
    prevValue.current = value;

    if (from === null || from === value) {
      setDisplay(value);
      return;
    }
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setDisplay(value);
      return;
    }

    const durationMs = 500;
    const start = performance.now();
    let raf = 0;
    function tick(now: number) {
      const progress = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(from! + (value - from!) * eased);
      if (progress < 1) raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);

  const rounded = Math.round(display);
  return <>{rounded.toLocaleString()}</>;
}

const STAT_CARD_ICON_STYLES: Record<string, string> = {
  brand: "bg-gradient-to-br from-violet-500 to-blue-500 text-white",
  success: "bg-gradient-to-br from-emerald-500 to-teal-500 text-white",
  danger: "bg-gradient-to-br from-rose-500 to-orange-500 text-white",
  neutral: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};

export function StatCard({
  label,
  value,
  tone = "neutral",
  icon,
  trend,
}: {
  label: string;
  value: ReactNode;
  tone?: "brand" | "success" | "danger" | "neutral";
  icon?: IconName;
  /** Small "+12% vs last period" style comparison (§20: one comparison per card). */
  trend?: { direction: "up" | "down"; label: string };
}) {
  const accents: Record<string, string> = {
    brand: "from-violet-500 to-blue-500",
    success: "from-emerald-500 to-teal-500",
    danger: "from-rose-500 to-orange-500",
    neutral: "from-slate-400 to-slate-500",
  };

  // tone="brand" is this app's generic "identity" accent (as opposed to
  // success/danger which are fixed status meanings, §18) — the one that
  // picks up the current company's own colors wherever it's used, across
  // every role's dashboard (CLAUDE.md §21).
  const branding = useBranding();
  const primary = tone === "brand" ? safeHex(branding.primaryColor) : undefined;
  const accent = tone === "brand" ? (safeHex(branding.accentColor) ?? primary) : undefined;
  const brandGradient = primary ? { backgroundImage: `linear-gradient(to right, ${primary}, ${accent})` } : undefined;
  const brandGradientBr = primary ? { backgroundImage: `linear-gradient(to bottom right, ${primary}, ${accent})` } : undefined;

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white px-4 py-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg dark:border-slate-800 dark:bg-slate-900/70 dark:backdrop-blur-sm">
      <span className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${accents[tone]}`} style={brandGradient} />
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</p>
          <p className="mt-1 text-2xl font-extrabold tracking-tight text-slate-900 dark:text-slate-50">
            {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
          </p>
        </div>
        {icon ? (
          <span
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${STAT_CARD_ICON_STYLES[tone]}`}
            style={brandGradientBr}
          >
            <Icon name={icon} className="h-4.5 w-4.5" />
          </span>
        ) : null}
      </div>
      {trend ? (
        <p
          className={`mt-1.5 flex items-center gap-1 text-xs font-semibold ${
            trend.direction === "up" ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
          }`}
        >
          <span aria-hidden="true">{trend.direction === "up" ? "↑" : "↓"}</span>
          {trend.label}
        </p>
      ) : null}
    </div>
  );
}

export function StatCardSkeleton() {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white px-4 py-4 dark:border-slate-800 dark:bg-slate-900/70">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="mt-2 h-7 w-28" />
    </div>
  );
}

/** §18/§20 quick-link tile: a real bordered card with an icon, not a row in a
 * plain `<ul>` — used for the "jump to a section" grid on every dashboard. */
export function LinkTile({
  to,
  icon,
  label,
  description,
}: {
  to: string;
  icon: IconName;
  label: string;
  description: string;
}) {
  return (
    // Hover accents read CSS vars AppShell sets from the current company's
    // brand colors (CLAUDE.md §21) — a plain `style` prop can't reach a
    // `:hover` pseudo-class, so this is the one spot that goes through CSS
    // custom properties instead of the BrandingContext hook every other
    // component here uses. The literal fallback after the comma is this
    // component's original platform-default violet/blue.
    <Link
      to={to}
      className="group flex items-start gap-3 rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm transition-all duration-150 hover:-translate-y-0.5 hover:border-[var(--brand-primary,#c4b5fd)] hover:shadow-lg hover:shadow-violet-500/10 dark:border-slate-800 dark:bg-slate-900/70 dark:hover:border-[var(--brand-primary,#6d28d9)]"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-50 text-violet-600 transition-all group-hover:bg-[image:linear-gradient(135deg,var(--brand-primary,#8b5cf6),var(--brand-accent,#3b82f6))] group-hover:text-white dark:bg-violet-950/50 dark:text-violet-400">
        <Icon name={icon} className="h-5 w-5" />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-slate-900 dark:text-slate-50">{label}</span>
        <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">{description}</span>
      </span>
    </Link>
  );
}

// Bolder consumer-fintech treatment: the hero's tone is either genuinely
// good/bad news (success/danger) or the neutral brand identity — each gets a
// full gradient surface with white text, so the "one verdict per screen"
// number (§20) reads as a statement, not a line item. "neutral" stays a
// plain card — reserved for a hero that isn't inherently good/bad news.
const HERO_SURFACE_TONES: Record<string, string> = {
  brand: "bg-gradient-to-br from-violet-600 via-indigo-600 to-blue-600 text-white shadow-xl shadow-indigo-600/25",
  success: "bg-gradient-to-br from-emerald-600 to-teal-600 text-white shadow-xl shadow-emerald-600/25",
  danger: "bg-gradient-to-br from-rose-600 to-orange-600 text-white shadow-xl shadow-rose-600/25",
  neutral:
    "bg-white text-slate-900 border border-slate-200/80 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.08)] dark:border-slate-800 dark:bg-slate-900 dark:text-slate-50 dark:shadow-[0_1px_2px_rgba(0,0,0,0.2),0_8px_24px_-12px_rgba(0,0,0,0.4)]",
};

const HERO_LABEL_TONES: Record<string, string> = {
  brand: "text-violet-100",
  success: "text-emerald-100",
  danger: "text-rose-100",
  neutral: "text-slate-400 dark:text-slate-500",
};

const HERO_SUBTEXT_TONES: Record<string, string> = {
  brand: "text-violet-100/80",
  success: "text-emerald-100/80",
  danger: "text-rose-100/80",
  neutral: "text-slate-500 dark:text-slate-400",
};

/** §20 "one verdict per screen": the single number a dashboard exists to
 * answer, given the top-left slot and the largest type — everything else on
 * the page supports it rather than competing with it. */
export function HeroStat({
  label,
  value,
  tone = "brand",
  subtext,
}: {
  label: string;
  value: ReactNode;
  tone?: "brand" | "success" | "danger" | "neutral";
  subtext?: ReactNode;
}) {
  const branding = useBranding();
  const primary = tone === "brand" ? safeHex(branding.primaryColor) : undefined;
  const accent = tone === "brand" ? (safeHex(branding.accentColor) ?? primary) : undefined;
  const brandStyle = primary
    ? { backgroundImage: `linear-gradient(to bottom right, ${primary}, ${accent})`, boxShadow: `0 20px 25px -5px ${primary}40` }
    : undefined;

  return (
    <div
      className={`relative flex h-full flex-col justify-center overflow-hidden rounded-3xl p-7 ${HERO_SURFACE_TONES[tone]}`}
      style={brandStyle}
    >
      {tone !== "neutral" ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10 blur-2xl"
        />
      ) : null}
      <p className={`relative text-xs font-semibold uppercase tracking-wider ${HERO_LABEL_TONES[tone]}`}>{label}</p>
      <p className="relative mt-2 text-6xl font-black tracking-tight">
        {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
      </p>
      {subtext ? <p className={`relative mt-2 text-sm ${HERO_SUBTEXT_TONES[tone]}`}>{subtext}</p> : null}
    </div>
  );
}

export function HeroStatSkeleton() {
  return (
    <div className="flex h-full flex-col justify-center rounded-3xl border border-slate-200/80 bg-white p-7 dark:border-slate-800 dark:bg-slate-900">
      <Skeleton className="h-3 w-32" />
      <Skeleton className="mt-3 h-14 w-40" />
      <Skeleton className="mt-3 h-4 w-48" />
    </div>
  );
}

const SPARKLINE_STROKES: Record<string, string> = {
  brand: "#6366f1",
  success: "#10b981",
  danger: "#f43f5e",
  neutral: "#94a3b8",
};

/** §20 KPI sparkline: a single-series trend line, thin (2px) stroke, no axes
 * or legend (one series needs none). A transparent circle per point carries a
 * native <title> so hovering still surfaces the exact value without building
 * a full crosshair for what is a small embedded decoration, not a standalone
 * chart. */
export function Sparkline({
  data,
  tone = "brand",
  height = 32,
  formatValue = (v) => v.toLocaleString(),
  showArea = false,
}: {
  data: number[];
  tone?: "brand" | "success" | "danger" | "neutral";
  height?: number;
  formatValue?: (value: number) => string;
  /** Gradient-faded fill under the line, same hue as the stroke (a single-
   * series magnitude encoding, not a new categorical color) — the "modern
   * fintech line chart" look, still one series so no legend is needed. */
  showArea?: boolean;
}) {
  const branding = useBranding();
  const gradientId = useId();
  if (data.length < 2) return null;
  const width = 100;
  const min = Math.min(...data);
  const max = Math.min(...data) === Math.max(...data) ? min + 1 : Math.max(...data);
  const range = max - min;
  const coords = data.map((v, i) => ({
    x: (i / (data.length - 1)) * width,
    y: height - ((v - min) / range) * (height - 4) - 2,
    v,
  }));
  const stroke = (tone === "brand" ? safeHex(branding.primaryColor) : undefined) ?? SPARKLINE_STROKES[tone];
  const last = coords[coords.length - 1];
  const linePoints = coords.map((c) => `${c.x},${c.y}`).join(" ");
  const areaPoints = `0,${height} ${linePoints} ${width},${height}`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="h-8 w-full overflow-visible">
      {showArea ? (
        <>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
              <stop offset="100%" stopColor={stroke} stopOpacity="0" />
            </linearGradient>
          </defs>
          <polygon points={areaPoints} fill={`url(#${gradientId})`} />
        </>
      ) : null}
      <polyline
        points={linePoints}
        fill="none"
        stroke={stroke}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={last.x} cy={last.y} r={2.5} fill={stroke} />
      {coords.map((c, i) => (
        <circle key={i} cx={c.x} cy={c.y} r={4} fill="transparent">
          <title>{formatValue(c.v)}</title>
        </circle>
      ))}
    </svg>
  );
}

const BAR_LIST_TONES: Record<string, { bar: string; text: string }> = {
  brand: { bar: "bg-indigo-500", text: "text-indigo-700 dark:text-indigo-300" },
  success: { bar: "bg-emerald-500", text: "text-emerald-700 dark:text-emerald-300" },
  warning: { bar: "bg-amber-500", text: "text-amber-700 dark:text-amber-300" },
  danger: { bar: "bg-rose-500", text: "text-rose-700 dark:text-rose-300" },
  neutral: { bar: "bg-slate-400", text: "text-slate-600 dark:text-slate-300" },
};

/** A magnitude-comparison bar list (dataviz skill: "the job picks the form" —
 * a handful of named categories compared by size is a bar chart, not a
 * sparkline or donut). Tones reuse this app's existing status-color meaning
 * (§18/§20: color means state, consistently) rather than an arbitrary
 * categorical palette, and every bar carries its own printed value — never
 * color alone. */
export function BarList({
  items,
  formatValue = (v) => v.toLocaleString(),
}: {
  items: { label: string; value: number; tone?: keyof typeof BAR_LIST_TONES }[];
  formatValue?: (value: number) => string;
}) {
  const branding = useBranding();
  const brandPrimary = safeHex(branding.primaryColor);
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="space-y-3">
      {items.map((item) => {
        const itemTone = item.tone ?? "neutral";
        const tone = BAR_LIST_TONES[itemTone];
        const pct = Math.max(2, Math.round((item.value / max) * 100));
        // "brand" bars pick up the tenant's own color (like every other
        // brand-toned accent, §21); status tones (success/warning/danger)
        // stay fixed everywhere per §18.
        const brandStyle = itemTone === "brand" && brandPrimary ? { backgroundColor: brandPrimary } : undefined;
        return (
          <li key={item.label}>
            <div className="mb-1 flex items-center justify-between gap-2 text-xs">
              <span className="font-medium text-slate-600 dark:text-slate-300">{item.label}</span>
              <span
                className={`font-semibold tabular-nums ${brandStyle ? "" : tone.text}`}
                style={brandStyle ? { color: brandPrimary } : undefined}
              >
                {formatValue(item.value)}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div
                className={`h-full rounded-full transition-[width] duration-500 ease-out ${brandStyle ? "" : tone.bar}`}
                style={{ width: `${pct}%`, ...brandStyle }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** A single value-against-a-max meter (credit utilization, repayment
 * progress) — the "bar" a magnitude comparison across categories
 * (`BarList`) doesn't cover: one quantity's share of one total. Always
 * prints both numbers next to the bar, never relies on fill length alone. */
export function UsageMeter({
  label,
  used,
  total,
  formatValue = (v) => v.toLocaleString(),
}: {
  label: string;
  used: number;
  total: number;
  formatValue?: (value: number) => string;
}) {
  const branding = useBranding();
  const primary = safeHex(branding.primaryColor);
  const accent = safeHex(branding.accentColor) ?? primary;
  const pct = total > 0 ? Math.min(100, Math.max(0, Math.round((used / total) * 100))) : 0;

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
        <span className="font-medium text-slate-600 dark:text-slate-300">{label}</span>
        <span className="font-semibold tabular-nums text-slate-500 dark:text-slate-400">
          {formatValue(used)} / {formatValue(total)} · {pct}%
        </span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        <div
          className={`h-full rounded-full transition-[width] duration-700 ease-out ${primary ? "" : "bg-gradient-to-r from-violet-500 to-blue-500"}`}
          style={{ width: `${pct}%`, backgroundImage: primary ? `linear-gradient(to right, ${primary}, ${accent})` : undefined }}
        />
      </div>
    </div>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg className={`h-4 w-4 animate-spin text-indigo-500 ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4Z" />
    </svg>
  );
}

export function LoadingRow({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-2 text-sm text-slate-500 dark:text-slate-400">
      <Spinner />
      {label}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/60 px-4 py-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-50">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
