import { clearAuth, loadAuth } from "../auth/storage";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : "Request failed");
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  /** Set false for the unauthenticated login/signup calls. Defaults to true. */
  auth?: boolean;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true } = options;
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  if (auth) {
    const stored = loadAuth();
    if (stored) {
      headers.Authorization = `Bearer ${stored.accessToken}`;
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (response.status === 401 && auth) {
    // CLAUDE.md §2: no refresh-token flow — on an expired/invalid token the
    // frontend simply re-prompts login, it doesn't try to silently recover.
    clearAuth();
    if (window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
    throw new ApiError(401, "Session expired");
  }

  const text = await response.text();
  const payload: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : payload;
    throw new ApiError(response.status, detail);
  }

  return payload as T;
}

/** POSTs multipart/form-data (KYC submission with file uploads). Never set
 * Content-Type manually here — the browser must generate the multipart
 * boundary itself. */
export async function apiRequestMultipart<T>(path: string, formData: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  const stored = loadAuth();
  if (stored) {
    headers.Authorization = `Bearer ${stored.accessToken}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { method: "POST", headers, body: formData });

  if (response.status === 401) {
    clearAuth();
    if (window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
    throw new ApiError(401, "Session expired");
  }

  const text = await response.text();
  const payload: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : payload;
    throw new ApiError(response.status, detail);
  }

  return payload as T;
}

/** Fetches a binary response (a KYC document) from an authenticated endpoint.
 * A plain <img src="..."> can't attach an Authorization header, so viewing an
 * uploaded document goes through this and gets rendered via a blob: URL. */
export async function fetchAuthedBlob(path: string): Promise<Blob> {
  const stored = loadAuth();
  const headers: Record<string, string> = {};
  if (stored) {
    headers.Authorization = `Bearer ${stored.accessToken}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { headers });

  if (response.status === 401) {
    clearAuth();
    if (window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
    throw new ApiError(401, "Session expired");
  }

  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }

  return response.blob();
}

/** Renders a FastAPI error `detail` (string, Pydantic validation list, or the
 * {code, message} shape used by the suspension gate) into one display string. */
export function formatApiErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : String(item)))
      .join("; ");
  }
  return "Something went wrong";
}

/** The one place every mutation's error handling should go through — was
 * previously the ternary `err instanceof ApiError ? formatApiErrorDetail(err.detail) : "Request failed"`
 * copy-pasted at ~23 call sites. */
export function getErrorMessage(err: unknown, fallback = "Request failed"): string {
  return err instanceof ApiError ? formatApiErrorDetail(err.detail) : fallback;
}

/** Builds a multipart FormData body from a react-hook-form values object plus
 * a map of file fields, skipping `undefined`/`null`/`""` values so an
 * unfilled optional field is omitted rather than sent as an empty string
 * (the backend's `Optional[str] = None` fields don't coerce `""` to `None`). */
export function buildMultipartForm(values: Record<string, unknown>, files: Record<string, File | null>): FormData {
  const formData = new FormData();
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null || value === "") continue;
    formData.append(key, String(value));
  }
  for (const [key, file] of Object.entries(files)) {
    if (file) formData.append(key, file);
  }
  return formData;
}
