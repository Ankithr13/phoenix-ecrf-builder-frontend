/* The only file that knows URLs. Pages call these functions and nothing
   else. Vite proxies /api to the backend in dev, so the session cookie is
   same-origin and travels with every request. */

import type { NewQuery, SubjectCreate,
  DashboardResponse, DataRow, DraftResponse, EcrfStatusOverview, FieldChange, Health, HistoryRow, HospitalSubmissionStatus, Me, NavigationContextData, NotificationPage, Plan,
  ProtocolListItem, ProtocolUploadResult, QueryRow, Reading, SiteRow, SponsorStudy, StudyCreate,
  StudyListItem, SubjectRow, VersionRow, WorkspaceOverview,
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

  sponsorStudies: () => req<SponsorStudy[]>("/api/sponsor/studies"),
  workspaceDashboard: () => req<WorkspaceOverview>("/api/sponsor/dashboard"),
  ecrfStatus: () => req<EcrfStatusOverview>("/api/sponsor/ecrf-status"),
  notifications: (filters: { before_id?: number; unread_only?: boolean; limit?: number } = {}) => {
    const query = new URLSearchParams(Object.entries(filters).map(([name, value]) => [name, String(value)]));
    return req<NotificationPage>(`/api/notifications${query.size ? `?${query}` : ""}`);
  },
  readNotification: (id: number) => req<{ read: boolean }>(`/api/notifications/${id}/read`, { method: "POST" }),
  readAllNotifications: (throughId: number) => req<{ read: boolean }>("/api/notifications/read-all", post({ through_id: throughId })),
  hospitalSubmission: (protocolId: number) => req<HospitalSubmissionStatus>(`/api/studies/${protocolId}/submission`),
  submitHospitalEcrf: (protocolId: number) => req<HospitalSubmissionStatus>(`/api/studies/${protocolId}/submission`, post({ confirmed: true })),
  sponsorStudy: (id: number) => req<SponsorStudy>(`/api/sponsor/studies/${id}`),
  navigationContext: (protocolId: string, subject?: string) =>
    req<NavigationContextData>(`/api/navigation/protocols/${protocolId}${subject === undefined ? "" : `?${new URLSearchParams({ subject })}`}`),
  createStudy: (body: StudyCreate) => req<SponsorStudy>("/api/sponsor/studies", post(body)),
  assignProtocolStudy: (protocolId: number, studyId: number | null) =>
    req<{ protocol_id: number; study_id: number | null }>(`/api/protocols/${protocolId}/study`, {
      method: "PUT", body: JSON.stringify({ study_id: studyId }),
    }),
  listProtocols: (filters: { study_id?: number; unassigned?: boolean } = {}) => {
    const query = new URLSearchParams();
    if (filters.study_id !== undefined) query.set("study_id", String(filters.study_id));
    if (filters.unassigned) query.set("unassigned", "true");
    return req<ProtocolListItem[]>(`/api/protocols${query.size ? `?${query}` : ""}`);
  },
  upload: (file: File, studyId: number) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("study_id", String(studyId));
    return req<ProtocolUploadResult>("/api/protocols/upload", { method: "POST", body: formData });
  },
  extract: (id: number, force = false) =>
    req<{ version: number }>(`/api/protocols/${id}/extract${force ? "?force=true" : ""}`, { method: "POST" }),
  extractVisits: (id: number, force = false) =>
    req<Plan>(`/api/protocols/${id}/extract/visits${force ? "?force=true" : ""}`, { method: "POST" }),
  visits: (id: number) => req<Plan>(`/api/protocols/${id}/visits`),
  saveVisits: (id: number, visits: string[]) => req<Plan>(`/api/protocols/${id}/visits`, { method: "PUT", body: JSON.stringify({ visits }) }),
  extractFields: (id: number, force = false) =>
    req<{ version: number }>(`/api/protocols/${id}/extract/fields${force ? "?force=true" : ""}`, { method: "POST" }),
  draft: (id: number) => req<DraftResponse>(`/api/protocols/${id}/draft`),
  versions: (id: number) => req<VersionRow[]>(`/api/protocols/${id}/versions`),
  section: (id: number, n: string) => req<{ number: string; title: string; page: number; text: string }>(`/api/protocols/${id}/section/${encodeURIComponent(n)}`),
  review: (id: number, changes: FieldChange[], note?: string, action: "save" | "approve_all_remaining" | "approve_suggested" = "save", include_guesses = false) =>
    req<{ version: number; applied: number }>(`/api/protocols/${id}/review`, post({ changes, note, action, include_guesses })),

  lock: (id: number) => req<{ version: number; state: string; locked_by: string }>(`/api/protocols/${id}/lock`, { method: "POST" }),

  sites: (id: number) => req<SiteRow[]>(`/api/protocols/${id}/sites`),
  assignSite: (id: number, site_org_id: number) => req<{ assigned: boolean }>(`/api/protocols/${id}/sites`, post({ site_org_id })),
  unassignSite: (id: number, site_org_id: number) => req<{ assigned: boolean }>(`/api/protocols/${id}/sites/${site_org_id}`, { method: "DELETE" }),

  studies: () => req<StudyListItem[]>("/api/studies"),
  subjects: (id: number) => req<SubjectRow[]>(`/api/studies/${id}/subjects`),
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
    req<{ ok: boolean; errors: Record<string, string> }>("/api/data/validate", post({ protocol_id, subject_id, visit, readings })),
  enter: (protocol_id: number, subject_id: string, visit: string, readings: Reading[]) =>
    req<{ saved: number }>("/api/data/enter", post({ protocol_id, subject_id, visit, readings })),
  seed: (id: number) => req<{ seeded: number; already: boolean }>(`/api/data/seed/${id}`, { method: "POST" }),

  dashboard: (id: number) => req<DashboardResponse>(`/api/dashboard/${id}`),

  queries: (status?: string) => req<QueryRow[]>(`/api/queries${status ? `?status=${status}` : ""}`),
  raiseQuery: (observationId: number, text: string) => req<QueryRow>(`/api/data/${observationId}/queries`, post({ text })),
  newQuery: (body: NewQuery) => req<QueryRow>("/api/queries", post(body)),
  answerQuery: (queryId: number, text: string, new_value?: string) =>
    req<QueryRow>(`/api/queries/${queryId}/answer`, post({ text, new_value: new_value === undefined || new_value === "" ? null : new_value })),
  closeQuery: (queryId: number) => req<QueryRow>(`/api/queries/${queryId}/close`, { method: "POST" }),
};
