/* The only file that knows URLs. Pages call these functions and nothing
   else. Vite proxies /api to the backend in dev, so the session cookie is
   same-origin and travels with every request. */

import type { AccessEvent, AdminOrg, AdminUser, CdashEntry, ChainRow, CheckWarning, EditCheck, FieldComment, FormHistoryRow, HistoryRow, LabRange, NewQuery, Role, SubjectCreate,
  DashboardResponse, DataRow, DraftResponse, FieldChange, Health, Me, Plan,
  ProtocolListItem, QueryRow, Reading, SiteRow, StudyListItem, SubjectRow, VersionRow,
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
  changePassword: (current_password: string, new_password: string) =>
    req<Me>("/api/auth/change-password", post({ current_password, new_password })),

  adminOrgs: () => req<AdminOrg[]>("/api/admin/orgs"),
  adminUsers: (filters: { org_id?: string; role?: string; active?: string } = {}) => {
    const q = new URLSearchParams(Object.entries(filters).filter(([, v]) => !!v) as [string, string][]);
    return req<AdminUser[]>(`/api/admin/users${q.toString() ? `?${q}` : ""}`);
  },
  adminCreateUser: (body: { email: string; name: string; org_id: number; role: Role; monitor_site_ids: number[] }) =>
    req<{ user: AdminUser; temporary_password: string }>("/api/admin/users", post(body)),
  adminEditUser: (id: number, body: { role?: Role; org_id?: number; monitor_site_ids?: number[] }) =>
    req<AdminUser>(`/api/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  adminDeactivate: (id: number) => req<AdminUser>(`/api/admin/users/${id}/deactivate`, { method: "POST" }),
  adminReactivate: (id: number) => req<AdminUser>(`/api/admin/users/${id}/reactivate`, { method: "POST" }),
  adminResetPassword: (id: number) =>
    req<{ user: AdminUser; temporary_password: string }>(`/api/admin/users/${id}/reset-password`, { method: "POST" }),
  adminAccessLog: () => req<AccessEvent[]>("/api/admin/access-log"),
  adminChain: () => req<ChainRow[]>("/api/admin/chain"),
  adminSetChain: (id: number, body: Partial<ChainRow>) =>
    req<ChainRow>(`/api/admin/chain/${id}`, { method: "PUT", body: JSON.stringify(body) }),

  listProtocols: () => req<ProtocolListItem[]>("/api/protocols"),
  loadSample: () => req<{ id: number; name: string }>("/api/protocols/sample", { method: "POST" }),
  upload: (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return req<{ id: number; name: string; pages: number; already_loaded?: boolean }>("/api/protocols/upload", { method: "POST", body: fd });
  },
  extractVisits: (id: number, force = false) =>
    req<Plan>(`/api/protocols/${id}/extract/visits${force ? "?force=true" : ""}`, { method: "POST" }),
  visits: (id: number) => req<Plan>(`/api/protocols/${id}/visits`),
  saveVisits: (id: number, visits: string[]) => req<Plan>(`/api/protocols/${id}/visits`, { method: "PUT", body: JSON.stringify({ visits }) }),
  extractFields: (id: number, force = false) =>
    req<{ version: number; replaced_draft: boolean }>(`/api/protocols/${id}/extract/fields${force ? "?force=true" : ""}`, { method: "POST" }),
  draft: (id: number) => req<DraftResponse>(`/api/protocols/${id}/draft`),
  versions: (id: number) => req<VersionRow[]>(`/api/protocols/${id}/versions`),
  section: (id: number, n: string) => req<{ number: string; title: string; page: number; text: string }>(`/api/protocols/${id}/section/${encodeURIComponent(n)}`),
  review: (id: number, changes: FieldChange[], note?: string, action: "save" | "approve_all_remaining" | "approve_suggested" = "save", include_guesses = false) =>
    req<{ version: number; applied: number }>(`/api/protocols/${id}/review`, post({ changes, note, action, include_guesses })),

  comments: (id: number) => req<FieldComment[]>(`/api/protocols/${id}/comments`),
  addComment: (id: number, field_id: string, body: string) => req<FieldComment>(`/api/protocols/${id}/comments`, post({ field_id, body })),
  resolveComment: (id: number, commentId: number) => req<FieldComment>(`/api/protocols/${id}/comments/${commentId}/resolve`, { method: "POST" }),
  formHistory: (id: number, fieldId: string) => req<FormHistoryRow[]>(`/api/protocols/${id}/form-history?field_id=${encodeURIComponent(fieldId)}`),
  cdashLibrary: () => req<CdashEntry[]>("/api/protocols/library/cdash"),
  labRanges: () => req<LabRange[]>("/api/protocols/library/lab-ranges"),

  checks: (id: number) => req<EditCheck[]>(`/api/protocols/${id}/checks`),
  addCheck: (id: number, body: { type: string; field_ids: string[]; logic: Record<string, unknown>; message: string; severity: string; form: string | null }) =>
    req<EditCheck>(`/api/protocols/${id}/checks`, post(body)),
  editCheck: (id: number, checkId: number, body: { enabled?: boolean; message?: string; reason?: string }) =>
    req<EditCheck>(`/api/protocols/${id}/checks/${checkId}`, { method: "PATCH", body: JSON.stringify(body) }),
  testCheck: (id: number, body: { type: string; field_ids: string[]; logic: Record<string, unknown>; sample: Record<string, string> }) =>
    req<{ passes: boolean | null }>(`/api/protocols/${id}/checks/test`, post(body)),

  lock: (id: number) => req<{ version: number; state: string; locked_by: string }>(`/api/protocols/${id}/lock`, { method: "POST" }),

  sites: (id: number) => req<SiteRow[]>(`/api/protocols/${id}/sites`),
  assignSite: (id: number, site_org_id: number) => req<{ assigned: boolean }>(`/api/protocols/${id}/sites`, post({ site_org_id })),
  unassignSite: (id: number, site_org_id: number, force = false) =>
    req<{ assigned: boolean }>(`/api/protocols/${id}/sites/${site_org_id}${force ? "?force=true" : ""}`, { method: "DELETE" }),

  studies: () => req<StudyListItem[]>("/api/studies"),
  subjects: (id: number, filters: { visit?: string; status?: string; open_queries?: string; needs_signoff?: string } = {}) => {
    const q = new URLSearchParams(Object.entries(filters).filter(([, v]) => !!v) as [string, string][]);
    return req<SubjectRow[]>(`/api/studies/${id}/subjects${q.toString() ? `?${q}` : ""}`);
  },
  createSubject: (id: number, body: SubjectCreate = {}) =>
    req<SubjectRow>(`/api/studies/${id}/subjects`, { method: "POST", body: JSON.stringify(body) }),

  dataRows: (id: number, filters: { site?: string; visit?: string; status?: string } = {}) => {
    const q = new URLSearchParams(Object.entries(filters).filter(([, v]) => !!v) as [string, string][]);
    return req<DataRow[]>(`/api/protocols/${id}/data${q.toString() ? `?${q}` : ""}`);
  },
  approveData: (id: number, observation_ids: number[]) =>
    req<{ approved: number }>(`/api/protocols/${id}/data/approve`, post({ observation_ids })),

  history: (id: number, observationId: number) => req<HistoryRow[]>(`/api/protocols/${id}/data/${observationId}/history`),

  validate: (protocol_id: number, subject_id: string, visit: string, readings: Reading[]) =>
    req<{ ok: boolean; errors: Record<string, string>; warnings: CheckWarning[] }>("/api/data/validate", post({ protocol_id, subject_id, visit, readings })),
  enter: (protocol_id: number, subject_id: string, visit: string, readings: Reading[], reason?: string) =>
    req<{ saved: number }>("/api/data/enter", post({ protocol_id, subject_id, visit, readings, reason })),
  submit: (protocol_id: number, subject_id: string, visit: string) =>
    req<{ submitted: number; queries: { id: number; code: string; text: string }[] }>("/api/data/submit", post({ protocol_id, subject_id, visit })),
  seed: (id: number) => req<{ seeded: number; already: boolean }>(`/api/data/seed/${id}`, { method: "POST" }),

  dashboard: (id: number) => req<DashboardResponse>(`/api/dashboard/${id}`),

  queries: (status?: string) => req<QueryRow[]>(`/api/queries${status ? `?status=${status}` : ""}`),
  raiseQuery: (observationId: number, text: string) => req<QueryRow>(`/api/data/${observationId}/queries`, post({ text })),
  newQuery: (body: NewQuery) => req<QueryRow>("/api/queries", post(body)),
  answerQuery: (queryId: number, text: string, new_value?: string) =>
    req<QueryRow>(`/api/queries/${queryId}/answer`, post({ text, new_value: new_value === undefined || new_value === "" ? null : new_value })),
  closeQuery: (queryId: number) => req<QueryRow>(`/api/queries/${queryId}/close`, { method: "POST" }),
};
