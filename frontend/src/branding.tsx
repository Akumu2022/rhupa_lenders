import { createContext, useContext } from "react";

/** CLAUDE.md §21: "tenant supplies DATA (a color, a logo, a name); the
 * platform controls the MECHANISM." AppShell resolves the logged-in staff/
 * customer's own company once (via /companies/me) and provides it here so
 * every shell surface — sidebar mark, page title, primary buttons — reads
 * the SAME resolved values instead of each re-fetching or hardcoding the
 * platform's own name. super_admin (no single company) and unauthenticated
 * pages (login/signup) get the default empty value, which every consumer
 * below treats as "fall back to platform branding" — branding is optional
 * polish, never required to function (§21).
 */
export interface Branding {
  name?: string | null;
  tagline?: string | null;
  logoUrl?: string | null;
  primaryColor?: string | null;
  accentColor?: string | null;
}

export const BrandingContext = createContext<Branding>({});

export function useBranding(): Branding {
  return useContext(BrandingContext);
}

const HEX_RE = /^#[0-9A-Fa-f]{6}$/;

/** Only ever feeds a validated hex value into an inline style — a malformed
 * value falls back to undefined (default styling) rather than producing
 * broken CSS (§21: a bad brand value is rejected at the door, not trusted). */
export function safeHex(value: string | null | undefined): string | undefined {
  return value && HEX_RE.test(value) ? value : undefined;
}
