import { useEffect, useState } from "react";
import type { CdashEntry, FieldChange, FieldComment, FieldDef, FieldType, LabRange, Status } from "../api/types";
import Badge from "./Badge";
import { HistoryButton } from "./HistoryDrawer";

interface Props {
  field: FieldDef;
  onChange: (change: Partial<FieldChange>) => void;
  onShowSection: (section: string) => void;
  readOnly?: boolean;
  comments?: FieldComment[];
  onComment?: (body: string) => Promise<void>;
  onResolve?: (commentId: number) => void;
  onHistory?: () => void;
  library?: CdashEntry[];
  labRanges?: LabRange[];
  // Set for a second after a decision, then the card moves to its new group.
  flash?: Status | null;
  moved?: boolean;
  editorId?: string;
  onEditingChange?: (id: string, editing: boolean) => void;
  onPendingRequestChange?: (id: string, pending: boolean) => void;
}

const FLASH_LABEL: Partial<Record<Status, string>> = { approved: "Approved", flagged: "Flagged", rejected: "Rejected" };
const OPTIONAL_FOUNDATION = ["Race", "Ethnicity"];

const TYPES: FieldType[] = ["integer", "decimal", "text", "date", "choice", "boolean"];

function metaLine(f: FieldDef): string {
  const parts: string[] = [f.type];
  if (f.unit) parts.push(f.unit);
  if (f.min !== null || f.max !== null) parts.push(`${f.min ?? "…"}–${f.max ?? "…"}`);
  if (f.repeats > 1) parts.push(`×${f.repeats}`);
  parts.push(f.required ? "required" : "optional");
  if (f.choices && f.choices.length) parts.push(f.choices.join(" / "));
  return parts.join(" · ");
}

function numOrNull(s: string): number | null {
  if (s.trim() === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

// What the editor holds while open. Strings throughout so the inputs are
// uncontrolled-friendly; converted on Apply.
interface Form {
  name: string;
  type: FieldType;
  unit: string;
  min: string;
  max: string;
  repeats: string;
  required: boolean;
  choices: string;
  allow_not_done: boolean;
  allow_not_applicable: boolean;
  allow_unknown: boolean;
}

function formFrom(f: FieldDef): Form {
  return {
    name: f.name,
    type: f.type,
    unit: f.unit ?? "",
    min: f.min === null ? "" : String(f.min),
    max: f.max === null ? "" : String(f.max),
    repeats: String(f.repeats),
    required: f.required,
    choices: (f.choices ?? []).join(", "),
    allow_not_done: f.allow_not_done ?? false,
    allow_not_applicable: f.allow_not_applicable ?? false,
    allow_unknown: f.allow_unknown ?? false,
  };
}

export default function FieldCard({ field, onChange, onShowSection, readOnly = false, comments = [], onComment, onResolve, onHistory, library, labRanges = [], flash = null, moved = false, editorId, onEditingChange, onPendingRequestChange }: Props) {
  const [editing, setEditing] = useState(false);
  const [showComments, setShowComments] = useState(false);
  const [draftComment, setDraftComment] = useState("");
  const [codeText, setCodeText] = useState("");
  const foundation = field.origin === "foundation";
  const openComments = comments.filter((c) => !c.resolved_at).length;
  const [showRanges, setShowRanges] = useState(false);
  const lowered = field.name.toLowerCase();
  const refRows = (field.type === "integer" || field.type === "decimal") && field.min === null && field.max === null
    ? labRanges.filter((r) => [r.name, ...(r.aliases ?? [])].some((n) => new RegExp(`\\b${n.toLowerCase().replace(/[^a-z0-9 ]/g, "")}\\b`).test(lowered)))
    : [];
  const pickCode = (text: string) => {
    setCodeText(text);
    const hit = library?.find((e) => `${e.name} (${e.cdash})` === text);
    if (hit) onChange({ cdash: hit.cdash });
  };
  const [form, setForm] = useState<Form>(() => formFrom(field));
  const [problem, setProblem] = useState<string | null>(null);
  const [commenting, setCommenting] = useState(false);
  const [commentError, setCommentError] = useState<string | null>(null);
  const hasPendingEditor = editing || draftComment.length > 0 || commenting;
  useEffect(() => {
    if (editorId === undefined || !onEditingChange) return;
    onEditingChange(editorId, hasPendingEditor);
    return () => onEditingChange(editorId, false);
  }, [editorId, hasPendingEditor, onEditingChange]);
  useEffect(() => {
    if (editorId === undefined || !onPendingRequestChange) return;
    onPendingRequestChange(editorId, commenting);
    return () => onPendingRequestChange(editorId, false);
  }, [editorId, commenting, onPendingRequestChange]);

  // Resync when the draft is reloaded (e.g. after a save) and the editor is closed.
  useEffect(() => { if (!editing) setForm(formFrom(field)); }, [field, editing]);

  const numeric = form.type === "integer" || form.type === "decimal";
  const set = (patch: Partial<Form>) => { setForm((p) => ({ ...p, ...patch })); setProblem(null); };

  const apply = () => {
    const change: Partial<FieldChange> = {};
    const name = form.name.trim();
    if (!name) { setProblem("A field needs a name."); return; }
    if (name !== field.name) change.new_name = name;
    if (form.type !== field.type) change.type = form.type;
    const unit = form.unit.trim();
    if (unit !== (field.unit ?? "")) change.unit = unit === "" ? null : unit;
    const min = numeric ? numOrNull(form.min) : null;
    const max = numeric ? numOrNull(form.max) : null;
    if (numeric && form.min.trim() !== "" && min === null) { setProblem("Minimum must be a number."); return; }
    if (numeric && form.max.trim() !== "" && max === null) { setProblem("Maximum must be a number."); return; }
    if (min !== null && max !== null && min > max) { setProblem("Minimum is above maximum."); return; }
    if (min !== field.min) change.min = min;
    if (max !== field.max) change.max = max;
    const repeats = Number(form.repeats);
    if (!Number.isInteger(repeats) || repeats < 1) { setProblem("Repeats must be a whole number of at least 1."); return; }
    if (repeats !== field.repeats) change.repeats = repeats;
    if (form.required !== field.required) change.required = form.required;
    const choices = form.type === "choice" ? form.choices.split(",").map((c) => c.trim()).filter(Boolean) : null;
    if (form.type === "choice" && (!choices || choices.length === 0)) { setProblem("A choice field needs at least one choice, separated by commas."); return; }
    if (JSON.stringify(choices) !== JSON.stringify(field.choices ?? null)) change.choices = choices;
    for (const key of ["allow_not_done", "allow_not_applicable", "allow_unknown"] as const) {
      if (form[key] !== (field[key] ?? false)) change[key] = form[key];
    }
    if (Object.keys(change).length > 0) onChange(change);
    setEditing(false);
  };

  const cancel = () => { setForm(formFrom(field)); setProblem(null); setEditing(false); };

  return (
    <div className={`field-card${editing ? " editing" : ""}${flash ? ` flash-${flash}` : ""}${moved ? " moved" : ""}`}>
      <div className="field-head">
        <span className="field-name">{field.name}</span>
        {field.cdash
          ? <span className="pill">{field.cdash}</span>
          : !foundation && <span className="pill chip-amber">no CDASH code</span>}
        {foundation && <span className="pill chip-brand">foundation</span>}
        {!field.collected && <span className="pill">not collected</span>}
        <span className="grow" />
        {flash && FLASH_LABEL[flash] && <span className="flash-label" role="status">{FLASH_LABEL[flash]}</span>}
        <button type="button" className="btn-link small" onClick={() => setShowComments((v) => !v)} aria-expanded={showComments}>
          comments{comments.length > 0 && <span className="tab-count">{openComments > 0 ? openComments : `${comments.length} resolved`}</span>}
        </button>
        {onHistory && <HistoryButton onClick={onHistory} label={`History of ${field.name}`} />}
        <Badge kind={field.status} />
      </div>
      <div className="field-meta">
        {metaLine(field)}
        {field.suggested && field.suggested.length > 0 && field.suggested_from === "protocol" && (
          <span className="pill chip-teal suggested" title={`${field.suggested.join(", ")} found stated in the protocol text; the sentence is in the note`}>
            {field.suggested.join(" · ")} found in protocol
          </span>
        )}
        {field.suggested && field.suggested.length > 0 && field.suggested_from === "library" && (
          <span className="pill chip-brand suggested" title={`${field.suggested.join(", ")} filled in from the CDASH library, not stated by the protocol`}>
            {field.suggested.join(" · ")} suggested by library
          </span>
        )}
        {field.suggested && field.suggested.length > 0 && field.suggested_from === "heuristic" && (
          <span className="pill chip-amber suggested" title="A plausibility range guessed from the unit or the field name. Not from the protocol or the library; check it.">
            range guessed
          </span>
        )}
      </div>

      {foundation ? (
        <div className="quote">
          <div className="small muted">Standard foundation field requested by the sponsor. It is on every protocol and quotes nothing, so the quote check does not apply.</div>
        </div>
      ) : (
      <div className={`quote quote-${field.verdict}`}>
        <div className="quote-text">"{field.source.quote}"</div>
        <div className="quote-row">
          <button type="button" className="btn-link" onClick={() => onShowSection(field.source.section)}>
            §{field.source.section}
          </button>
          <Badge kind={field.verdict} />
          <span className="mono small muted">{field.match_score ?? "–"}%</span>
        </div>
      </div>
      )}

      {!readOnly && !field.cdash && !foundation && library && (
        <div className="row row-wrap mt-2">
          <label className="ctl ctl-wide">
            Pick a CDASH code by name
            <input className="input input-sm input-grow" list={`cdash-${field.field_id}`} value={codeText}
                   onChange={(e) => pickCode(e.target.value)} placeholder="Search the library" aria-label={`CDASH code for ${field.name}`} />
          </label>
          <datalist id={`cdash-${field.field_id}`}>
            {library.map((e) => <option key={`${e.domain}-${e.cdash}`} value={`${e.name} (${e.cdash})`} />)}
          </datalist>
        </div>
      )}

      {!readOnly && refRows.length > 0 && (
        <div className="mt-2">
          <button type="button" className="btn-link small" onClick={() => setShowRanges((v) => !v)}>Suggest range from reference table</button>
          {showRanges && (
            <div className="comment-thread">
              <p className="xs muted">Unconfirmed until Denise confirms it. Nothing is applied unless you choose it, and the field stays yours to edit.</p>
              {refRows.map((r) => (
                <div className="row row-wrap mt-2" key={`${r.name}-${r.sex ?? ""}`}>
                  <span className="small">{r.name}{r.sex ? ` (${r.sex})` : ""}: <span className="mono">{r.low} to {r.high} {r.unit}</span></span>
                  <a className="inline xs" href={r.source} target="_blank" rel="noreferrer">source</a>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => { onChange({ min: r.low, max: r.high, unit: r.unit }); setShowRanges(false); }}>Use this</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {showComments && (
        <div className="comment-thread">
          {comments.length === 0 && <p className="muted small">No comments on this field.</p>}
          {comments.map((c) => (
            <div className={`comment${c.resolved_at ? " resolved" : ""}`} key={c.id}>
              <div className="xs muted">{c.author} · {new Date(c.created_at).toLocaleString()} · v{c.version}{c.resolved_at ? ` · resolved by ${c.resolved_by}` : ""}</div>
              <div className="small">{c.body}</div>
              {!c.resolved_at && onResolve && <button type="button" className="btn-link small" onClick={() => onResolve(c.id)}>Resolve</button>}
            </div>
          ))}
          {onComment && (
            <div className="row mt-2">
              <input className="input input-sm grow" value={draftComment} onChange={(e) => setDraftComment(e.target.value)} placeholder="Add a comment" aria-label={`Comment on ${field.name}`} disabled={commenting} />
              <button type="button" className="btn btn-secondary btn-sm" disabled={!draftComment.trim() || commenting}
                      onClick={async () => { setCommenting(true); setCommentError(null); try { await onComment(draftComment.trim()); setDraftComment(""); } catch { setCommentError("Could not save your comment. Your text is kept here; check the comment history before retrying."); } finally { setCommenting(false); } }}>{commenting ? "Saving…" : "Add"}</button>
              <button type="button" className="btn btn-secondary btn-sm" disabled={commenting || !draftComment} onClick={() => { setDraftComment(""); setCommentError(null); }}>Discard comment</button>
              {commentError && <span className="error" role="alert">{commentError}</span>}
            </div>
          )}
        </div>
      )}

      {field.issue !== "none" && (
        <div className="issue-banner">
          <span className="issue-word">{field.issue}</span>
          <span>{field.issue_note}</span>
        </div>
      )}

      {!readOnly && editing && (
        <div className="field-editor">
          {!foundation && (
            <>
              <label className="ctl ctl-wide">
                name
                <input className="input input-sm input-grow" value={form.name} onChange={(e) => set({ name: e.target.value })} aria-label="Field name" />
              </label>
              <label className="ctl">
                type
                <select className="input input-sm" value={form.type} onChange={(e) => set({ type: e.target.value as FieldType })} aria-label="Field type">
                  {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
            </>
          )}
          {numeric && (
            <>
              <label className="ctl">
                unit
                <input className="input input-sm" value={form.unit} onChange={(e) => set({ unit: e.target.value })} placeholder="e.g. mmHg" aria-label="Unit" />
              </label>
              <label className="ctl">
                min
                <input className="input input-sm input-mono" type="number" value={form.min} onChange={(e) => set({ min: e.target.value })} aria-label="Minimum" />
              </label>
              <label className="ctl">
                max
                <input className="input input-sm input-mono" type="number" value={form.max} onChange={(e) => set({ max: e.target.value })} aria-label="Maximum" />
              </label>
            </>
          )}
          {form.type === "choice" && (
            <label className="ctl ctl-wide">
              choices
              <input className="input input-sm input-grow" value={form.choices} onChange={(e) => set({ choices: e.target.value })} placeholder="Yes, No, Not done" aria-label="Choices, comma separated" />
            </label>
          )}
          <label className="ctl">
            repeats
            <input className="input input-sm input-mono" type="number" min={1} step={1} value={form.repeats} onChange={(e) => set({ repeats: e.target.value })} aria-label="Repeats" />
          </label>
          <label className="ctl">
            <input type="checkbox" checked={form.required} onChange={(e) => set({ required: e.target.checked })} aria-label="Required" />
            required
          </label>
          <label className="ctl">
            <input type="checkbox" checked={form.allow_not_done} onChange={(e) => set({ allow_not_done: e.target.checked })} aria-label="Allow not done" />
            not done allowed
          </label>
          <label className="ctl">
            <input type="checkbox" checked={form.allow_not_applicable} onChange={(e) => set({ allow_not_applicable: e.target.checked })} aria-label="Allow not applicable" />
            not applicable allowed
          </label>
          <label className="ctl">
            <input type="checkbox" checked={form.allow_unknown} onChange={(e) => set({ allow_unknown: e.target.checked })} aria-label="Allow unknown" />
            unknown allowed
          </label>
          <span className="grow" />
          {problem && <span className="error small">{problem}</span>}
          <button type="button" className="btn btn-primary btn-sm" onClick={apply}>Apply</button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={cancel}>Cancel</button>
          <p className="small muted editor-note">The quote and section cannot be edited: they are what the protocol says, and the grounding check depends on them. Applied edits are pending until you save the review.</p>
        </div>
      )}

      {!readOnly && !editing && <div className="field-controls">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>Edit</button>
        <span className="grow" />
        <button type="button" className="btn btn-teal btn-sm" onClick={() => onChange({ status: "approved" })}>Approve</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => onChange({ status: "flagged" })}>Flag</button>
        {foundation
          ? OPTIONAL_FOUNDATION.includes(field.name) && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onChange({ collected: !field.collected })}>
              {field.collected ? "Mark not collected" : "Collect this field"}
            </button>
          )
          : <button type="button" className="btn btn-danger btn-sm" onClick={() => onChange({ status: "rejected" })}>Reject</button>}
      </div>}
    </div>
  );
}
