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
  cdash: string | null;
  domain: string | null;
  // what the CDASH library filled in because the protocol was silent
  suggested: string[];
  suggested_from: "protocol" | "library" | "heuristic" | null;
  field_id: string;
  origin: "model" | "foundation";
  collected: boolean;
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
  est_cost_usd?: number | null;
}

export interface PlanUsage {
  llm_calls_made: number;
  llm_calls_from_cache: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  est_cost_usd: number | null;
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
  lock_warnings?: LockWarning[];
  plan?: Plan | null;
}

/* Approved fields a site will struggle with. Shown next to the Lock
   button; none of them block the lock. */
export interface LockWarning {
  kind: "choice_without_choices" | "numeric_without_range" | "numeric_without_unit";
  count: number;
  fields: string[];
  text: string;
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
  name: string;          // identifies the field; a rename goes in new_name
  status?: Status;
  new_name?: string;
  type?: FieldType;
  unit?: string | null;
  min?: number | null;
  max?: number | null;
  required?: boolean;
  repeats?: number;
  choices?: string[] | null;
  reviewer_note?: string;
  collected?: boolean;
  cdash?: string;
}

export interface FieldComment {
  id: number;
  version: number;
  field_id: string;
  author: string;
  body: string;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface FormHistoryRow {
  id: number;
  version: number;
  field_id: string | null;
  attribute: string;
  old_value: string | null;
  new_value: string | null;
  by: string;
  at: string;
  reason: string | null;
}

export interface CdashEntry {
  cdash: string;
  name: string;
  domain: string;
}

export interface HistoryRow {
  old_value: string | null;
  new_value: string | null;
  changed_by: string;
  changed_at: string;
  reason: string | null;
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
  // not_available when either side could not compute it; never a pass
  status: "pass" | "fail" | "not_available";
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
export type Role = "admin" | "builder" | "data_manager" | "monitor" | "read_only"
  | "investigator" | "site_coordinator" | "site_data_entry";

export interface Me {
  user: { id: number; name: string; email: string };
  org: { id: number; name: string; type: OrgType; code: string };
  role: Role;
  permissions: string[];
  must_change_password: boolean;
}

export interface AdminOrg {
  id: number;
  name: string;
  code: string;
  type: OrgType;
  roles: Role[];
}

export interface AdminUser {
  id: number;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  created_by: string | null;
  created_at: string;
  last_login_at: string | null;
  org: { id: number; name: string; code: string; type: OrgType };
  monitor_site_ids: number[];
}

export interface AccessEvent {
  id: number;
  user: string;
  action: string;
  by: string;
  at: string;
  detail: string | null;
}

export interface ChainRow {
  id: number;
  name: string;
  monitor_review_required: boolean;
  investigator_signature_required: boolean;
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
  birth_year: number | null;
  sex: string | null;
  enrolled_on: string | null;
  note: string | null;
}

/* Registration. Everything optional; the code always comes from the server.
   No name, no initials, no full date of birth: a CRF is pseudonymous. */
export interface SubjectCreate {
  birth_year?: number;
  sex?: string;
  enrolled_on?: string;
  note?: string;
}

export type ObservationStatus = "submitted" | "approved" | "queried";

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

export interface Health {
  ok: boolean;
  version: string;
  backend: string;
  model: string;
  context_mode: string;
  quote_match_threshold: number;
}

export type QueryStatus = "open" | "answered" | "closed";

export interface QueryRow {
  id: number;
  protocol_id: number;
  protocol_name: string | null;
  // What the question is about: the study as a whole, one patient, one
  // visit of a patient, or one entered value. Narrower levels fill in more
  // of the fields below.
  about: "study" | "patient" | "visit" | "value";
  site: string | null;
  site_name: string | null;
  subject: string | null;
  visit: string | null;
  observation_id: number | null;
  field: string | null;
  repeat: number | null;
  value: string | null;
  observation_status: ObservationStatus | null;
  status: QueryStatus;
  text: string;
  raised_by: string;
  raised_by_org: "sponsor" | "site";
  raised_at: string;
  answer_text: string | null;
  answered_by: string | null;
  answered_at: string | null;
  closed_by: string | null;
  closed_at: string | null;
  // For the signed-in user: their turn to answer, or theirs to close.
  can_answer: boolean;
  can_close: boolean;
  for_me: boolean;
}

export interface NewQuery {
  protocol_id: number;
  text: string;
  site_org_id?: number;
  subject_code?: string;
  visit?: string;
  observation_id?: number;
}
