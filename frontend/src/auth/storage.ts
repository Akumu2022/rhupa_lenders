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

export function loadAuth(): StoredAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredAuth) : null;
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
