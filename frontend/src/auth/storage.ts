// CLAUDE.md §2: access tokens are short-lived and there is no refresh-token
// flow in the MVP — the frontend simply re-prompts login on expiry. Auth
// state is stored client-side only for convenience across reloads; the
// backend is the sole source of truth on every request.
const STORAGE_KEY = "rupha.auth";

export interface StoredAuth {
  accessToken: string;
  role: string;
  companyId: number | null;
}

/** The JWT's `exp` claim in epoch milliseconds, or null if it can't be read. */
export function tokenExpiryMs(token: string): number | null {
  try {
    const part = token.split(".")[1];
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = (JSON.parse(json) as { exp?: number }).exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}

export function loadAuth(): StoredAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const auth = JSON.parse(raw) as StoredAuth;
    // An expired (or unreadable) token is no session at all — drop it here so
    // the app opens on the login page instead of a dashboard that 401s.
    const expiry = tokenExpiryMs(auth.accessToken);
    if (expiry === null || expiry <= Date.now()) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return auth;
  } catch {
    return null;
  }
}

export function saveAuth(auth: StoredAuth): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(auth));
}

export function clearAuth(): void {
  localStorage.removeItem(STORAGE_KEY);
}
