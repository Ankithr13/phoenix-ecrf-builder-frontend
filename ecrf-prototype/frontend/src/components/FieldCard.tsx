import { useEffect, useState } from "react";
import type { FieldChange, FieldDef, FieldType } from "../api/types";
import Badge from "./Badge";

interface Props {
  field: FieldDef;
  onChange: (change: Partial<FieldChange>) => void;
  onShowSection: (section: string) => void;
  readOnly?: boolean;
}

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
  };
}

export default function FieldCard({ field, onChange, onShowSection, readOnly = false }: Props) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Form>(() => formFrom(field));
  const [problem, setProblem] = useState<string | null>(null);

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
    if (Object.keys(change).length > 0) onChange(change);
    setEditing(false);
  };

  const cancel = () => { setForm(formFrom(field)); setProblem(null); setEditing(false); };

  return (
    <div className={`field-card${editing ? " editing" : ""}`}>
      <div className="field-head">
        <span className="field-name">{field.name}</span>
        {field.cdash && <span className="pill">{field.cdash}</span>}
        <span className="grow" />
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

      <div className={`quote quote-${field.verdict}`}>
        <div className="quote-text">"{field.source.quote}"</div>
        <div className="quote-row">
          <button type="button" className="btn-link" onClick={() => onShowSection(field.source.section)}>
            §{field.source.section}
          </button>
          <Badge kind={field.verdict} />
          <span className="mono small muted">{field.match_score ?? "–"}%</span>
          {/* field.section_ok is deliberately NOT shown. Section detection
              treats table-of-contents lines as sections and finds some
              section numbers twice, so the check reported a mismatch for
              roughly half of all fields on a long protocol, most of them
              wrongly. The backend still computes it; put it back on screen
              only once ingest.py stops mistaking contents lines for
              sections. */}
        </div>
      </div>

      {field.issue !== "none" && (
        <div className="issue-banner">
          <span className="issue-word">{field.issue}</span>
          <span>{field.issue_note}</span>
        </div>
      )}

      {!readOnly && editing && (
        <div className="field-editor">
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
        <button type="button" className="btn btn-danger btn-sm" onClick={() => onChange({ status: "rejected" })}>Reject</button>
      </div>}
    </div>
  );
}
