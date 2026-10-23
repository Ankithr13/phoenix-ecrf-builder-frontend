/* The only file that knows URLs. Pages call these functions and nothing
   else. Vite proxies /api to the backend in dev, so the session cookie is
   same-origin and travels with every request. */

import type {
  DashboardResponse, DraftResponse, FieldChange, Health, Me,
  ProtocolListItem, Reading, StudyListItem, VersionRow,
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    // Same message shape pages already parse: "422 {...}".
    super(`${status} ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
    this.status = status;
    this.detail = detail;
  }
}

/* The AuthProvider registers what to do on a 401 (send the user to the
   login page). Calls that expect a 401 as a normal answer opt out. */
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) { onUnauthorized = fn; }

async function req<T>(path: string, init: RequestInit = {}, opts: { allow401?: boolean } = {}): Promise<T> {
  const r = await fetch(path, {
    credentials: "include",
    ...init,
    headers: { ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(init.headers || {}) },
  });
  if (!r.ok) {
    let detail: unknown = r.statusText;
    try { detail = (await r.json()).detail; } catch { /* ignore */ }
    if (r.status === 401 && !opts.allow401 && onUnauthorized) onUnauthorized();
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => req<Health>("/api/health"),

  me: () => req<Me>("/api/auth/me", {}, { allow401: true }),
  login: (email: string, password: string) => req<Me>("/api/auth/login", post({ email, password }), { allow401: true }),
  logout: () => req<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),

  listProtocols: () => req<ProtocolListItem[]>("/api/protocols"),
  loadSample: () => req<{ id: number; name: string }>("/api/protocols/sample", { method: "POST" }),
  upload: (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return req<{ id: number; name: string; pages: number; already_loaded?: boolean }>("/api/protocols/upload", { method: "POST", body: fd });
  },
  extract: (id: number, force = false) =>
    req<{ version: number }>(`/api/protocols/${id}/extract${force ? "?force=true" : ""}`, { method: "POST" }),
  draft: (id: number) => req<DraftResponse>(`/api/protocols/${id}/draft`),
  versions: (id: number) => req<VersionRow[]>(`/api/protocols/${id}/versions`),
  section: (id: number, n: string) => req<{ number: string; title: string; page: number; text: string }>(`/api/protocols/${id}/section/${encodeURIComponent(n)}`),
  review: (id: number, changes: FieldChange[], note?: string, action: "save" | "approve_all_remaining" = "save") =>
    req<{ version: number; applied: number }>(`/api/protocols/${id}/review`, post({ changes, note, action })),

  studies: () => req<StudyListItem[]>("/api/studies"),

  validate: (protocol_id: number, subject_id: string, visit: string, readings: Reading[]) =>
    req<{ ok: boolean; errors: Record<string, string> }>("/api/data/validate", post({ protocol_id, subject_id, visit, readings })),
  enter: (protocol_id: number, subject_id: string, visit: string, readings: Reading[]) =>
    req<{ saved: number }>("/api/data/enter", post({ protocol_id, subject_id, visit, readings })),
  seed: (id: number) => req<{ seeded: number; already: boolean }>(`/api/data/seed/${id}`, { method: "POST" }),

  dashboard: (id: number) => req<DashboardResponse>(`/api/dashboard/${id}`),
};
