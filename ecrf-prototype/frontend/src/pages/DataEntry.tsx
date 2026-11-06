import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { CheckWarning, CompletionStatus, DataRow, DraftResponse, FieldDef, Reading, SignoffRow, SubjectRow } from "../api/types";
import { useAuth } from "../auth/useAuth";
import HistoryDrawer, { HistoryButton, type HistoryLine } from "../components/HistoryDrawer";
import { DERIVED, INPUTS, LABEL, compute, roleOf } from "../derive";

type Values = Record<string, string>;
type Completion = Record<string, { status: CompletionStatus; reason: string }>;

const slot = (name: string, rep: number) => `${name}#${rep}`;
const REASON_MIN = 5;
const COMPLETION_LABEL: Record<CompletionStatus, string> = {
  value: "Value", not_done: "Not done", not_applicable: "Not applicable", unknown: "Unknown",
};

/* What the server would refuse outright. A range or a blank is not here: those
   are soft checks, which save and raise a query at submit. */
function formatError(f: FieldDef, s: string): string | null {
  if (s.trim() === "") return null;
  if (f.type === "integer" || f.type === "decimal") {
    const x = Number(s);
    if (!Number.isFinite(x)) return "must be a number";
    if (f.type === "integer" && x !== Math.trunc(x)) return "must be a whole number";
  }
  if (f.type === "choice" && f.choices && !f.choices.includes(s)) return `must be one of: ${f.choices.join(", ")}`;
  return null;
}

function rangeNote(f: FieldDef, s: string): string | null {
  if (s.trim() === "" || (f.type !== "integer" && f.type !== "decimal")) return null;
  const x = Number(s);
  if (!Number.isFinite(x)) return null;
  if (f.min !== null && x < f.min) return `below ${f.min}: this will raise a query on submit`;
  if (f.max !== null && x > f.max) return `above ${f.max}: this will raise a query on submit`;
  return null;
}

function rowValue(r: DataRow): string {
  if (r.completion_status !== "value" || r.value === null) return "";
  if (r.value === "Yes") return "true";
  if (r.value === "No") return "false";
  return r.value;
}

function serverErrors(e: unknown): Record<string, string> | null {
  const detail = e instanceof ApiError ? (e.detail as { errors?: Record<string, string> }) : null;
  return detail && typeof detail === "object" && detail.errors ? detail.errors : null;
}

/* One patient's visit form. Values are drafts and save as you go, until the
   site submits the visit. After that a change needs a reason. */
export default function DataEntry() {
  const { id: idParam, subject: subjectParam } = useParams();
  const id = Number(idParam);
  const subject = subjectParam ?? "";
  const { me, can } = useAuth();
  const [resp, setResp] = useState<DraftResponse | null>(null);
  const [visit, setVisit] = useState("");
  const [values, setValues] = useState<Values>({});
  const [completion, setCompletion] = useState<Completion>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState<Set<string>>(new Set());
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [rows, setRows] = useState<DataRow[]>([]);
  const [patient, setPatient] = useState<SubjectRow | null>(null);
  const [confirming, setConfirming] = useState<CheckWarning[] | null>(null);
  const [show, setShow] = useState<"" | "queries" | "not_done">("");
  const [asking, setAsking] = useState<{ id: number; text: string } | null>(null);
  const [drawer, setDrawer] = useState<{ title: string; lines: HistoryLine[] | null } | null>(null);
  // Saves go one at a time. Two at once would each miss the other's value, and
  // a derived value such as BMI needs both of its inputs on file.
  const saves = useRef<Promise<unknown>>(Promise.resolve());
  const [signoffs, setSignoffs] = useState<SignoffRow[]>([]);
  const [meaning, setMeaning] = useState("");
  const [signing, setSigning] = useState(false);
  const [password, setPassword] = useState("");

  const loadSignoffs = useCallback(() => {
    api.signoffs(id, subject).then((r) => { setSignoffs(r.rows); setMeaning(r.meaning); }).catch(() => setSignoffs([]));
  }, [id, subject]);
  useEffect(() => { loadSignoffs(); }, [loadSignoffs, rows]);

  useEffect(() => {
    api.subjects(id).then((all) => setPatient(all.find((r) => r.code === subject) ?? null)).catch(() => setPatient(null));
  }, [id, subject]);

  const loadRows = useCallback(async () => {
    const all = (await api.dataRows(id)).filter((r) => r.subject === subject);
    setRows(all);
    return all;
  }, [id, subject]);

  // What is on file for this visit fills the form. Anything being edited stays.
  const fill = useCallback((all: DataRow[], forVisit: string, keep: Set<string>) => {
    setValues((prev) => {
      const next: Values = {};
      for (const k of keep) if (prev[k] !== undefined) next[k] = prev[k];
      for (const r of all) if (r.visit === forVisit && !keep.has(slot(r.field, r.repeat))) next[slot(r.field, r.repeat)] = rowValue(r);
      return next;
    });
    setCompletion((prev) => {
      const next: Completion = {};
      for (const k of keep) if (prev[k]) next[k] = prev[k];
      for (const r of all) {
        const k = slot(r.field, r.repeat);
        if (r.visit === forVisit && !keep.has(k) && r.completion_status !== "value") {
          next[k] = { status: r.completion_status, reason: r.completion_reason ?? "" };
        }
      }
      return next;
    });
  }, []);

  useEffect(() => {
    api.draft(id).then((r) => {
      setResp(r);
      const first = r.draft?.forms[0]?.visit ?? "";
      setVisit(first);
      return loadRows().then((all) => fill(all, first, new Set()));
    }).catch((e) => setMessage({ kind: "error", text: (e as Error).message }));
  }, [id, loadRows, fill]);

  const changeVisit = (v: string) => {
    setVisit(v); setErrors({}); setMessage(null); setDirty(new Set()); setReason(""); setConfirming(null);
    fill(rows, v, new Set());
  };

  const fields = useMemo(() => {
    const form = resp?.draft?.forms.find((f) => f.visit === visit);
    // A locked form only carries approved and rejected fields; only the
    // approved ones are collected.
    return (form?.fields ?? []).filter((f) => f.status === "approved" && f.collected !== false);
  }, [resp, visit]);

  const rowAt = useMemo(() => {
    const m: Record<string, DataRow> = {};
    for (const r of rows) if (r.visit === visit) m[slot(r.field, r.repeat)] = r;
    return m;
  }, [rows, visit]);
  const hasDraft = rows.some((r) => r.visit === visit && r.status === "draft");

  // Values that follow from others, filled in as the inputs are typed. The
  // server recomputes them and refuses one that disagrees.
  const derived = useMemo(() => {
    const inputs: Record<string, { value: number; unit: string | null }> = {};
    for (const f of fields) {
      const role = roleOf(f, INPUTS);
      if (!role || inputs[role]) continue;
      const v = values[slot(f.name, 1)];
      // A date counts by its year, the only part age at consent needs.
      const n = v === undefined || v === "" ? NaN : Number(f.type === "date" ? String(v).slice(0, 4) : v);
      if (Number.isFinite(n)) inputs[role] = { value: n, unit: f.unit };
    }
    return compute(inputs, patient ? { birth_year: patient.birth_year, sex: patient.sex } : null);
  }, [fields, values, patient]);
  const derivedFields = useMemo(() => {
    const out: Record<string, FieldDef> = {};
    for (const f of fields) { const k = roleOf(f, DERIVED); if (k && !out[k]) out[k] = f; }
    return out;
  }, [fields]);
  useEffect(() => {
    setValues((prev) => {
      let next = prev; let changed = false;
      for (const d of derived) {
        const f = derivedFields[d.key];
        if (!f) continue;
        const k = slot(f.name, 1);
        const want = f.type === "integer" ? String(Math.round(d.value)) : String(d.value);
        if (prev[k] !== want) { if (!changed) { next = { ...prev }; changed = true; } next[k] = want; }
      }
      return changed ? next : prev;
    });
  }, [derived, derivedFields]);
  const calculatedFor = (f: FieldDef): string | null => {
    const k = roleOf(f, DERIVED);
    const d = k ? derived.find((x) => x.key === k) : undefined;
    return d ? `calculated from ${d.from}` : null;
  };

  const reading = (f: FieldDef, rep: number, raw: string, c?: { status: CompletionStatus; reason: string }): Reading => {
    const done = c && c.status !== "value";
    let value: Reading["value"] = done || raw === "" ? null : raw;
    if (!done && f.type === "boolean" && raw !== "") value = raw === "true";
    return { field_name: f.name, repeat_num: rep, value, completion_status: c?.status ?? "value", completion_reason: done ? c.reason : null };
  };

  /* A draft saves straight away. A submitted or approved value waits in `dirty`
     until it has a reason. */
  const persist = async (f: FieldDef, rep: number, raw: string, c?: { status: CompletionStatus; reason: string }) => {
    const k = slot(f.name, rep);
    const row = rowAt[k];
    const unchanged = row
      ? rowValue(row) === raw && row.completion_status === (c?.status ?? "value") && (row.completion_reason ?? "") === (c?.status && c.status !== "value" ? c.reason : "")
      : raw === "" && (c?.status ?? "value") === "value";
    if (unchanged) { setDirty((d) => { const n = new Set(d); n.delete(k); return n; }); return; }
    if (c && c.status !== "value" && !c.reason.trim()) return;
    if (formatError(f, raw)) { setErrors((e) => ({ ...e, [k]: formatError(f, raw) as string })); return; }
    if (row && row.status !== "draft") { setDirty((d) => new Set(d).add(k)); return; }
    const job = saves.current.then(async () => {
      try {
        await api.enter(id, subject, visit, [reading(f, rep, raw, c)]);
        setErrors((e) => { const n = { ...e }; delete n[k]; return n; });
        setMessage(null);
        await loadRows();
      } catch (e) {
        const errs = serverErrors(e);
        if (errs) setErrors((prev) => ({ ...prev, ...errs }));
        else setMessage({ kind: "error", text: (e as Error).message });
      }
    });
    saves.current = job;
    await job;
  };

  const saveChanges = async () => {
    setSaving(true); setMessage(null);
    const readings: Reading[] = [];
    for (const f of fields) {
      for (let i = 1; i <= Math.max(1, f.repeats); i++) {
        const k = slot(f.name, i);
        if (dirty.has(k)) readings.push(reading(f, i, values[k] ?? "", completion[k]));
      }
    }
    try {
      await api.enter(id, subject, visit, readings, reason.trim());
      const n = new Set<string>();
      setDirty(n); setReason(""); setErrors({});
      setMessage({ kind: "ok", text: `${readings.length} change${readings.length === 1 ? "" : "s"} saved. These values go back for review.` });
      fill(await loadRows(), visit, n);
    } catch (e) {
      const errs = serverErrors(e);
      if (errs) { setErrors(errs); setMessage({ kind: "error", text: "Fix the highlighted fields." }); }
      else setMessage({ kind: "error", text: (e as Error).message });
    } finally { setSaving(false); }
  };

  const askSubmit = async () => {
    setMessage(null);
    try {
      await saves.current;
      const check = await api.validate(id, subject, visit, []);
      setConfirming(check.warnings ?? []);
    } catch (e) { setMessage({ kind: "error", text: (e as Error).message }); }
  };

  const doSubmit = async () => {
    setSaving(true);
    try {
      await saves.current;
      const r = await api.submit(id, subject, visit);
      setConfirming(null);
      setMessage({ kind: "ok", text: `${r.submitted} value${r.submitted === 1 ? "" : "s"} submitted for ${visit}.${r.queries.length ? ` ${r.queries.length} quer${r.queries.length === 1 ? "y" : "ies"} raised.` : ""}` });
      fill(await loadRows(), visit, new Set());
    } catch (e) {
      setConfirming(null);
      const errs = serverErrors(e);
      if (errs) { setErrors(errs); setMessage({ kind: "error", text: "These must be fixed before this visit can be submitted." }); }
      else setMessage({ kind: "error", text: (e as Error).message });
    } finally { setSaving(false); }
  };

  const visitRows = rows.filter((r) => r.visit === visit);
  const validSignoff = signoffs.find((x) => x.visit === visit && !x.invalidated_at);
  const undone = !validSignoff && signoffs.some((x) => x.visit === visit && x.invalidated_at);
  const openOnPatient = patient?.open_queries ?? 0;
  const readyToSign = visitRows.length > 0 && visitRows.every((r) => r.status === "approved") && openOnPatient === 0;
  const sign = async () => {
    setSaving(true); setMessage(null);
    try {
      await api.sign(id, subject, visit, password);
      setSigning(false); setPassword("");
      setMessage({ kind: "ok", text: `${visit} signed.` });
      loadSignoffs();
    } catch (e) {
      const detail = e instanceof ApiError ? e.detail : null;
      setMessage({ kind: "error", text: typeof detail === "string" ? detail : (detail as { message?: string })?.message ?? (e as Error).message });
    } finally { setSaving(false); }
  };

  const ask = async () => {
    if (!asking || !asking.text.trim()) return;
    try {
      await api.raiseQuery(asking.id, asking.text.trim());
      setAsking(null);
      await loadRows();
      setMessage({ kind: "ok", text: "Query sent to the sponsor. Track it under Queries." });
    } catch (e) { setMessage({ kind: "error", text: (e as Error).message }); }
  };

  const showHistory = async (r: DataRow) => {
    const title = `${r.field} · history`;
    setDrawer({ title, lines: null });
    const hist = await api.history(id, r.id);
    setDrawer({ title, lines: hist.map((h, i) => ({ key: i, old_value: h.old_value, new_value: h.new_value, who: h.changed_by, when: h.changed_at, reason: h.reason })) });
  };

  if (!resp) return <div className="page">{message ? <p className="error">{message.text}</p> : <p className="muted">Loading…</p>}</div>;

  if (!resp.draft) {
    return (
      <div className="page">
        <h1 className="page-title">Data entry</h1>
        <div className="card"><p className="strong">Form not available</p><p className="muted small mt-2">The sponsor has not locked this form yet.</p></div>
      </div>
    );
  }

  const shownField = (f: FieldDef) => {
    if (!show) return true;
    return Array.from({ length: Math.max(1, f.repeats) }, (_, i) => rowAt[slot(f.name, i + 1)]).some((r) =>
      show === "queries" ? (r?.open_query_count ?? 0) > 0 : r?.completion_status === "not_done");
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Data entry</h1>
        <p className="muted small">Synthetic data only. No real patient information is entered into this prototype.</p>
      </div>
      {resp.study_locked_at && <div className="lock-banner"><span className="strong">Study locked.</span> <span>No data on this study can change.</span></div>}

      <div className="card">
        <div className="row row-wrap row-between">
          <div className="row row-wrap">
            <div>
              <div className="label">Patient</div>
              <div className="mono strong">{subject}</div>
            </div>
            <div>
              <label className="label" htmlFor="visit">Visit</label>
              <select id="visit" className="input" value={visit} onChange={(e) => changeVisit(e.target.value)}>
                {resp.draft.forms.map((f) => <option key={f.visit} value={f.visit}>{f.visit}</option>)}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="show">Show</label>
              <select id="show" className="input" value={show} onChange={(e) => setShow(e.target.value as typeof show)}>
                <option value="">All fields</option>
                <option value="queries">Fields with open queries</option>
                <option value="not_done">Fields not done</option>
              </select>
            </div>
          </div>
          <div className="small muted">
            {me?.org.name} · <Link className="inline" to={`/site/s/${id}/patients`}>all patients</Link>
          </div>
        </div>
      </div>

      <div className="card mt-4">
        <div className="section-title">{visit} · {resp.protocol.name}</div>
        {fields.length === 0 && <p className="muted small">No fields for this visit.</p>}
        <div className="entry-grid">
          {fields.filter(shownField).flatMap((f) =>
            Array.from({ length: Math.max(1, f.repeats) }, (_, i) => {
              const rep = i + 1;
              const k = slot(f.name, rep);
              const row = rowAt[k];
              const raw = values[k] ?? "";
              const c = completion[k];
              const notValue = !!c && c.status !== "value";
              const err = errors[k] ?? (notValue ? null : formatError(f, raw));
              const note = notValue ? null : rangeNote(f, raw);
              const label = f.repeats > 1 ? `${f.name} · Reading ${rep}` : f.name;
              const hint = [f.unit, f.min !== null || f.max !== null ? `${f.min ?? "…"}–${f.max ?? "…"}` : null, f.cdash].filter(Boolean).join(" · ");
              const allowed: CompletionStatus[] = [
                ...(f.allow_not_done ? ["not_done" as const] : []),
                ...(f.allow_not_applicable ? ["not_applicable" as const] : []),
                ...(f.allow_unknown ? ["unknown" as const] : []),
              ];
              const set = (v: string) => { setValues((p) => ({ ...p, [k]: v })); setErrors((e) => { const n = { ...e }; delete n[k]; return n; }); };
              const setNow = (v: string) => { set(v); persist(f, rep, v, c); };
              const blur = () => persist(f, rep, raw, c);
              const cls = `input${err ? " input-invalid" : ""}`;
              let control;
              if (notValue) {
                control = null;
              } else if (f.type === "boolean") {
                // Two explicit answers and a blank. Not answered is not No.
                control = (
                  <div className="yesno" role="radiogroup" aria-label={label}>
                    {(["true", "false"] as const).map((opt) => (
                      <label key={opt} className={`check yesno-opt${raw === opt ? " active" : ""}${err ? " invalid" : ""}`}>
                        <input type="radio" name={k} value={opt} checked={raw === opt} onChange={() => setNow(opt)} />
                        {opt === "true" ? "Yes" : "No"}
                      </label>
                    ))}
                    {raw !== "" && <button type="button" className="btn-link small" onClick={() => setNow("")}>clear</button>}
                  </div>
                );
              } else if (f.type === "choice" && f.choices) {
                control = (
                  <select id={k} className={cls} value={raw} onChange={(e) => setNow(e.target.value)}>
                    <option value="">—</option>
                    {f.choices.map((x) => <option key={x} value={x}>{x}</option>)}
                  </select>
                );
              } else if (f.type === "integer" || f.type === "decimal") {
                control = <input id={k} className={cls} type="number" step={f.type === "integer" ? 1 : "any"} value={raw} onChange={(e) => set(e.target.value)} onBlur={blur} />;
              } else if (f.type === "date") {
                control = <input id={k} className={cls} type="date" value={raw} onChange={(e) => set(e.target.value)} onBlur={blur} />;
              } else {
                control = <input id={k} className={cls} type="text" value={raw} onChange={(e) => set(e.target.value)} onBlur={blur} />;
              }
              return (
                <div className="entry-field" key={k}>
                  <label className="label" htmlFor={k}>
                    {label}{f.required && <span className="req" aria-label="required">*</span>}
                    {row && row.status !== "draft" && <span className="pill entry-status">{row.status.replace("_", " ")}</span>}
                    {(row?.open_query_count ?? 0) > 0 && <span className="pill chip-rust entry-status">{row.open_query_count} open query</span>}
                    {dirty.has(k) && <span className="pill chip-amber entry-status">changed</span>}
                  </label>
                  {allowed.length > 0 && (
                    <select className="input input-sm completion" value={c?.status ?? "value"} aria-label={`How ${label} was completed`}
                            onChange={(e) => {
                              const status = e.target.value as CompletionStatus;
                              const next = { status, reason: c?.reason ?? "" };
                              setCompletion((p) => ({ ...p, [k]: next }));
                              if (status !== "value") setValues((p) => ({ ...p, [k]: "" }));
                              if (status === "value") persist(f, rep, "", next);
                            }}>
                      {(["value", ...allowed] as CompletionStatus[]).map((x) => <option key={x} value={x}>{COMPLETION_LABEL[x]}</option>)}
                    </select>
                  )}
                  {control}
                  {notValue && (
                    <input className="input input-sm completion-reason" placeholder={`Why ${COMPLETION_LABEL[c.status].toLowerCase()}?`} value={c.reason} aria-label={`Reason for ${label}`}
                           onChange={(e) => setCompletion((p) => ({ ...p, [k]: { ...c, reason: e.target.value } }))}
                           onBlur={() => persist(f, rep, "", c)} />
                  )}
                  {calculatedFor(f) && <span className="hint calc">{calculatedFor(f)}</span>}
                  {hint && <span className="hint">{hint}</span>}
                  {note && <span className="check-note">{note}</span>}
                  {err && <span className="error">{err}</span>}
                </div>
              );
            }),
          )}
        </div>

        {derived.length > 0 && (
          <div className="calc-panel mt-4">
            <span className="strong small">Calculated</span>
            {derived.map((d) => (
              <span key={d.key} className="calc-item" title={`from ${d.from}`}>
                {LABEL[d.key]} <span className="mono">{d.value} {d.unit}</span>
                {derivedFields[d.key] ? <span className="xs muted"> · filled in</span> : <span className="xs muted"> · not a field on this form</span>}
              </span>
            ))}
          </div>
        )}

        {dirty.size > 0 && (
          <div className="row row-wrap mt-4">
            <input className="input grow" placeholder={`Reason for change, at least ${REASON_MIN} characters`} value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason for change" />
            <button type="button" className="btn btn-primary" onClick={saveChanges} disabled={saving || reason.trim().length < REASON_MIN}>
              Save {dirty.size} change{dirty.size === 1 ? "" : "s"}
            </button>
          </div>
        )}

        {confirming && (
          <div className="card card-amber mt-4">
            <p className="strong">Submit {visit}?</p>
            {confirming.length === 0
              ? <p className="small mt-2">Every check passes. The sponsor will see these values.</p>
              : (
                <>
                  <p className="small mt-2">The sponsor will see these values, and {confirming.length} quer{confirming.length === 1 ? "y" : "ies"} will be raised:</p>
                  <ul className="warn-list">
                    {confirming.map((w, i) => <li key={i}><span className="mono xs">{w.code}</span> {w.message}</li>)}
                  </ul>
                </>
              )}
            <div className="row mt-3">
              <button type="button" className="btn btn-primary btn-sm" onClick={doSubmit} disabled={saving}>{saving ? "Submitting…" : "Submit visit"}</button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setConfirming(null)}>Keep editing</button>
            </div>
          </div>
        )}

        <div className="row mt-5">
          {can("data.submit") && hasDraft && !confirming && !resp.study_locked_at && (
            <button type="button" className="btn btn-primary" onClick={askSubmit} disabled={saving || dirty.size > 0}>Submit visit</button>
          )}
          <span className="small muted">{hasDraft ? "Drafts save as you go. The sponsor sees nothing until you submit." : ""}</span>
          {message && <span className={message.kind === "ok" ? "ok" : "error"}>{message.text}</span>}
        </div>
      </div>

      {resp.investigator_signature_required && visitRows.length > 0 && (
        <div className={`card mt-4${undone ? " card-rust" : ""}`}>
          <div className="section-title">Investigator sign-off</div>
          {validSignoff && <p className="small">Signed by {validSignoff.signed_by} on {new Date(validSignoff.signed_at).toLocaleString()}.</p>}
          {undone && <p className="small strong">Needs re-sign. A value changed after this visit was signed.</p>}
          {!validSignoff && !readyToSign && (
            <p className="muted small">
              Sign-off opens once every value at this visit is approved and no query is open on this patient
              {openOnPatient > 0 ? ` (${openOnPatient} open now)` : ""}.
            </p>
          )}
          {!validSignoff && readyToSign && can("signoff.sign") && !signing && !resp.study_locked_at && (
            <button type="button" className="btn btn-primary btn-sm" onClick={() => setSigning(true)}>Sign off this visit</button>
          )}
          {!validSignoff && readyToSign && !can("signoff.sign") && <p className="muted small">Ready for the investigator to sign.</p>}
          {signing && (
            <div className="mt-3">
              <p className="small">{meaning}</p>
              <div className="row row-wrap mt-2">
                <input className="input input-sm" type="password" autoComplete="current-password" placeholder="Enter your password again"
                       aria-label="Your password" value={password} onChange={(e) => setPassword(e.target.value)} />
                <button type="button" className="btn btn-primary btn-sm" onClick={sign} disabled={saving || !password}>Sign</button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setSigning(false); setPassword(""); }}>Cancel</button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="card mt-4">
        <div className="row row-between row-wrap">
          <p className="strong">On file for {subject}</p>
          {can("listing.view") && patient && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => {
              api.casebookPdf(patient.id, patient.code).catch((e) => setMessage({ kind: "error", text: (e as Error).message }));
            }}>Casebook PDF</button>
          )}
          <p className="muted small">Ask the sponsor about any value. An approved value can be changed only while the sponsor has a query open on it.</p>
        </div>
        {rows.length === 0 && <p className="muted small mt-2">Nothing saved for this patient yet.</p>}
        {rows.length > 0 && (
          <table className="table mt-2">
            <thead><tr><th>Visit</th><th>Field</th><th>Value</th><th>Status</th><th /></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.visit}</td>
                  <td>{r.field}{r.repeat > 1 ? ` · ${r.repeat}` : ""}</td>
                  <td className="mono">{r.value ?? "—"}</td>
                  <td>
                    <span className={`pill ${r.status === "approved" ? "chip-teal" : r.status === "draft" ? "" : "chip-amber"}`}>{r.status.replace("_", " ")}</span>
                    {r.open_query_count > 0 && <span className="pill chip-rust entry-status">{r.open_query_count} open query</span>}
                  </td>
                  <td className="num">
                    <HistoryButton onClick={() => showHistory(r)} label={`History of ${r.field}`} />
                    {r.open_query_count === 0 && can("query.raise") && (
                      <button type="button" className="btn-link" onClick={() => setAsking({ id: r.id, text: "" })}>Ask the sponsor</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {asking && (
          <div className="row row-wrap mt-3 query-reply">
            <input className="input grow" autoFocus placeholder="Your question about this value, e.g. which unit do you want?"
                   value={asking.text} onChange={(e) => setAsking({ ...asking, text: e.target.value })} />
            <button type="button" className="btn btn-primary btn-sm" onClick={ask} disabled={!asking.text.trim()}>Send query</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAsking(null)}>Cancel</button>
          </div>
        )}
      </div>
      {drawer && <HistoryDrawer title={drawer.title} lines={drawer.lines} onClose={() => setDrawer(null)} />}
    </div>
  );
}
