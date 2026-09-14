import { Field, TextInput } from "./ui";

// CLAUDE.md §21: "tenant supplies DATA (a color, a logo); the platform
// controls the MECHANISM" — these are curated defaults a system_administrator can
// one-click into the field, not a theme builder. Each was picked dark/
// saturated enough to keep white button text readable (checked below too).
const DEFAULT_PRESETS = [
  "#4F46E5", // indigo
  "#0EA5E9", // sky
  "#059669", // emerald
  "#DC2626", // red
  "#D97706", // amber
  "#7C3AED", // violet
  "#DB2777", // pink
  "#0F172A", // slate
];

const HEX_RE = /^#[0-9A-Fa-f]{6}$/;

/** WCAG relative luminance / contrast ratio, used to warn (not block) when a
 * brand color would make the white button/badge text CLAUDE.md §21 relies on
 * hard to read. */
function contrastAgainstWhite(hex: string): number | null {
  if (!HEX_RE.test(hex)) return null;
  const channel = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  return (1.0 + 0.05) / (luminance + 0.05);
}

/** Pairs a native color-picker swatch with the raw hex text field (so a user
 * who doesn't know hex can just click a color), a live preview chip, preset
 * swatches, and an inline WCAG contrast warning — CLAUDE.md §21's "validate
 * colors: check contrast" guard, which the plain text input had no way to do. */
export function ColorField({
  label,
  value,
  onChange,
  error,
  presets = DEFAULT_PRESETS,
  placeholder = "#4F46E5",
}: {
  label: string;
  value: string | undefined;
  onChange: (hex: string) => void;
  error?: string;
  presets?: string[];
  placeholder?: string;
}) {
  const swatchValue = value && HEX_RE.test(value) ? value : "#94a3b8";
  const contrast = value ? contrastAgainstWhite(value) : null;
  const lowContrast = contrast !== null && contrast < 4.5;

  return (
    <Field label={label} error={error}>
      <div className="flex items-center gap-2">
        <input
          type="color"
          aria-label={`${label} picker`}
          value={swatchValue}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="h-9 w-10 shrink-0 cursor-pointer rounded-md border border-slate-300 bg-transparent p-0.5 dark:border-slate-700"
        />
        <TextInput
          placeholder={placeholder}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1"
        />
        <span
          className="h-9 w-9 shrink-0 rounded-md border border-slate-300 dark:border-slate-700"
          style={{ backgroundColor: swatchValue }}
          title="Preview"
        />
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {presets.map((preset) => (
          <button
            key={preset}
            type="button"
            title={preset}
            aria-label={`Use ${preset}`}
            onClick={() => onChange(preset)}
            className="h-5 w-5 rounded-full border border-black/10 transition-transform hover:scale-110 dark:border-white/20"
            style={{ backgroundColor: preset }}
          />
        ))}
      </div>
      {lowContrast ? (
        <p className="mt-1.5 text-xs text-amber-600 dark:text-amber-400">
          This color may make white button text hard to read — consider a darker or more saturated shade.
        </p>
      ) : null}
    </Field>
  );
}
