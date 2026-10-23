/* Mirrors backend/ecrf/schema.py and the API responses. If the backend
   changes, change this file. Nothing else in the frontend declares shapes. */

export type FieldType = "integer" | "decimal" | "text" | "date" | "choice" | "boolean";
export type Issue = "none" | "missing" | "conflicting" | "ambiguous" | "unsupported";
export type Status = "draft" | "approved" | "flagged" | "rejected";
export type Verdict = "exact" | "approximate" | "rejected" | "unchecked";

export interface Source {
  section: string;
  quote: string;
}

export interface FieldDef {
  name: string;
  type: FieldType;
  required: boolean;
  unit: string | null;
  repeats: number;
  choices: string[] | null;
  min: number | null;
  max: number | null;
  source: Source;
  issue: Issue;
  issue_note: string | null;
  status: Status;
  verdict: Verdict;
  match_score: number | null;
  section_ok: boolean | null;
  cdash: string | null;
  domain: string | null;
}

export interface VisitForm {
  visit: string;
  form: string;
  fields: FieldDef[];
}

export interface Rejection {
  visit: string;
  name: string;
  quote: string;
  section: string;
  score: number;
  reason: string;
}

export interface Summary {
  visits: number;
  fields_generated: number;
  fields_kept: number;
  exact: number;
  approximate: number;
  rejected: number;
  flagged: number;
  threshold: number;
  seconds: number;
  // stage 4, present on new extractions
  strategy?: string;
  forms?: number;
  llm_calls_made?: number;
  llm_calls_from_cache?: number;
  input_tokens?: number;
  cached_input_tokens?: number;
  output_tokens?: number;
  reasoning_tokens?: number;
  est_cost_usd?: number;
}

export interface PlanUsage {
  llm_calls_made: number;
  llm_calls_from_cache: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  est_cost_usd: number;
}

export interface Plan {
  visits: string[];
  forms: { name: string; visits: string[] }[];
  confirmed: boolean;
  usage: PlanUsage | null;
  strategy: string;
  estimated_calls: number;
}

export interface DraftECRF {
  protocol_id: number;
  protocol_hash: string;
  version: number;
  backend: string;
  model: string;
  forms: VisitForm[];
  rejections: Rejection[];
  summary: Summary;
}

export interface LibrarySuggestion {
  domain: string;
  name: string;
  cdash: string;
  type: string | null;
  unit: string | null;
}

export interface ProtocolListItem {
  id: number;
  name: string;
  filename: string;
  pages: number;
  tokens_estimate: number;
  uploaded_by: string;
  uploaded_at: string;
  latest_version: number | null;
  state: "draft" | "locked" | null;
  summary: Summary | null;
  plan: Plan | null;
}

export interface DraftResponse {
  protocol: { id: number; name: string; pages: number; tokens_estimate: number; hash: string };
  version: number | null;
  created_by?: string;
  created_at?: string;
  note?: string | null;
  draft: DraftECRF | null;
  library_suggestions?: Record<string, LibrarySuggestion[]>;
  state?: "draft" | "locked";
  locked_by?: string | null;
  locked_at?: string | null;
  lock_blockers?: { draft: number; flagged: number };
  plan?: Plan | null;
}

export interface VersionRow {
  version: number;
  created_by: string;
  created_at: string;
  note: string | null;
  summary: Summary | null;
}

export interface FieldChange {
  visit: string;
  name: string;
  status?: Status;
  min?: number | null;
  max?: number | null;
  required?: boolean;
  repeats?: number;
}

export interface Reading {
  field_name: string;
  repeat_num: number;
  value: string | number | boolean | null;
}

export interface StatResult {
  name: string;
  label: string;
  unit: string;
  kind: "scalar" | "by_visit";
  // null when the statistic could not be computed for this protocol
  app: number | Record<string, number> | null;
  independent: number | Record<string, number> | null;
  pass: boolean;
}

export interface DashboardResponse {
  protocol: { id: number; name: string };
  extraction: {
    version: number;
    summary: Summary;
    per_visit: { visit: string; fields: number; flagged: number; approved: number }[];
    rejections: number;
    backend: string;
    model: string;
  } | null;
  // readings counts approved rows only; entered_total counts every row
  data: { subjects: number; readings: number; entered_total: number };
  stats: StatResult[];
}

export type OrgType = "sponsor" | "site";
export type Role = "builder" | "approver" | "site_staff";

export interface Me {
  user: { id: number; name: string; email: string };
  org: { id: number; name: string; type: OrgType; code: string };
  role: Role;
  permissions: string[];
}

export interface StudyListItem {
  id: number;
  name: string;
  pages: number;
  locked_at: string | null;
  visits: string[];
  subjects: number;
}

export interface SiteRow {
  org_id: number;
  name: string;
  code: string;
  assigned: boolean;
}

export interface SubjectRow {
  id: number;
  code: string;
  site: string | null;
  site_name: string | null;
  created_by: string;
  created_at: string;
  readings: number;
}

export type ObservationStatus = "entered" | "approved" | "queried";

export interface DataRow {
  id: number;
  site: string | null;
  subject: string;
  visit: string;
  field: string;
  repeat: number;
  value: string | null;
  status: ObservationStatus;
  entered_by: string;
  entered_at: string;
  updated_at: string | null;
  approved_by: string | null;
}

export interface HistoryRow {
  old_value: string | null;
  new_value: string | null;
  changed_by: string;
  changed_at: string;
  reason: string | null;
}

export interface Health {
  ok: boolean;
  version: string;
  backend: string;
  model: string;
  context_mode: string;
  quote_match_threshold: number;
}
