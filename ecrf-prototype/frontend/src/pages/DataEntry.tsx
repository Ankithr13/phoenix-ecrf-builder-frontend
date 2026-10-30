import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { DataRow, DraftResponse, FieldDef, Reading } from "../api/types";
import { useAuth } from "../auth/useAuth";

type Values = Record<string, string | boolean>;

const slot = (name: string, rep: number) => `${name}#${rep}`;

/* Mirrors backend/ecrf/api/data.py validate(). The server check is the
   guarantee; this one is for immediate feedback. */
function validate(f: FieldDef, v: string | boolean | undefined): string | null {
  if (f.type === "boolean") return null;
  const s = v === undefined || v === null ? "" : String(v);
  if (s.trim() === "") return f.required ? "required" : null;
  if (f.type === "integer" || f.type === "decimal") {
    const x = Number(s);
    if (!Number.isFinite(x)) return "must be a number";
    if (f.type === "integer" && x !== Math.trunc(x)) return "must be a whole number";
    if (f.min !== null && x < f.min) return `below minimum ${f.min}`;
    if (f.max !== null && x > f.max) return `above maximum ${f.max}`;
  }
  if (f.type === "choice" && f.choices && !f.choices.includes(s)) {
    return `must be one of: ${f.choices.join(", ")}`;
  }
  return null;
}

function parseServerErrors(message: string): Record<string, string> | null {
  // client.ts throws "422 {\"errors\":{...}}"
  const i = message.indexOf("{");
  if (i < 0) return null;
  try {
    const obj = JSON.parse(message.slice(i));
    return obj && typeof obj === "object" && obj.errors ? obj.errors : null;
  } catch { return null; }
}

export default function DataEntry() {
  const { id: idParam, subject: subjectParam } = useParams();
  const id = Number(idParam);
  const subject = subjectParam ?? "";
  const { me } = useAuth();
  const [resp, setResp] = useState<DraftResponse | null>(null);
  const [visit, setVisit] = useState("");
  const [values, setValues] = useState<Values>({});
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [entered, setEntered] = useState<DataRow[]>([]);
  const [asking, setAsking] = useState<{ id: number; text: string } | null>(null);
  const [askBusy, setAskBusy] = useState(false);

  // What this patient already has on file, with a way to ask the sponsor
  // about any value. The rows come back scoped to this site.
  const loadEntered = useCallback(async () => {
    try { setEntered((await api.dataRows(id)).filter((r) => r.subject === subject)); }
    catch { setEntered([]); }
  }, [id, subject]);
  useEffect(() => { loadEntered(); }, [loadEntered]);

  const ask = async () => {
    if (!asking || !asking.text.trim()) return;
    setAskBusy(true);
    try {
      await api.raiseQuery(asking.id, asking.text.trim());
      setAsking(null);
      await loadEntered();
      setMessage({ kind: "ok", text: "Query sent to the sponsor. Track it under Queries." });
    } catch (e) { setMessage({ kind: "error", text: (e as Error).message }); }
    finally { setAskBusy(false); }
  };

  const load = useCallback(async () => {
    try {
      const r = await api.draft(id);
      setResp(r);
      setVisit((v) => v || r.draft?.forms[0]?.visit || "");
    } catch (e) {
      setMessage({ kind: "error", text: (e as Error).message });
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const fields = useMemo(() => {
    const form = resp?.draft?.forms.find((f) => f.visit === visit);
    // A locked form only carries approved and rejected fields; only the
    // approved ones are collected.
    return (form?.fields ?? []).filter((f) => f.status === "approved");
  }, [resp, visit]);

  const set = (k: string, v: string | boolean) => {
    setValues((prev) => ({ ...prev, [k]: v }));
    setServerErrors((prev) => { if (!(k in prev)) return prev; const n = { ...prev }; delete n[k]; return n; });
    setTouched(true);
  };

  const changeVisit = (v: string) => {
    setVisit(v); setValues({}); setServerErrors({}); setMessage(null); setTouched(false);
  };

  const readings = (): Reading[] =>
    fields.flatMap((f) =>
      Array.from({ length: Math.max(1, f.repeats) }, (_, i) => {
        const k = slot(f.name, i + 1);
        const v = values[k];
        let value: Reading["value"];
        if (f.type === "boolean") value = v === true;
        else value = v === undefined || v === "" ? null : String(v);
        return { field_name: f.name, repeat_num: i + 1, value };
      }),
    );

  const clientErrors = useMemo(() => {
    const out: Record<string, string> = {};
    for (const f of fields) {
      for (let i = 1; i <= Math.max(1, f.repeats); i++) {
        const k = slot(f.name, i);
        const err = validate(f, values[k]);
        if (err) out[k] = err;
      }
    }
    return out;
  }, [fields, values]);

  const errorFor = (k: string) => serverErrors[k] ?? (touched ? clientErrors[k] : undefined);

  const save = async () => {
    setTouched(true); setMessage(null); setServerErrors({});
    if (Object.keys(clientErrors).length) {
      setMessage({ kind: "error", text: "Fix the highlighted fields before saving." });
      return;
    }
    setSaving(true);
    try {
      const check = await api.validate(id, subject, visit, readings());
      if (!check.ok) {
        setServerErrors(check.errors);
        setMessage({ kind: "error", text: "The server rejected some readings." });
        return;
      }
      const r = await api.enter(id, subject, visit, readings());
      setMessage({ kind: "ok", text: `${r.saved} readings saved for ${subject} at ${visit}.` });
      await loadEntered();
    } catch (e) {
      const errs = parseServerErrors((e as Error).message);
      if (errs) { setServerErrors(errs); setMessage({ kind: "error", text: "The server rejected some readings." }); }
      else setMessage({ kind: "error", text: (e as Error).message });
    } finally {
      setSaving(false);
    }
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

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Data entry</h1>
        <p className="muted small">Synthetic data only. No real patient information is entered into this prototype.</p>
      </div>

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
          </div>
          <div className="small muted">
            {me?.org.name} · <Link className="inline" to={`/site/s/${id}/patients`}>all patients</Link>
          </div>
        </div>
      </div>

      <div className="card mt-4">
        <div className="section-title">{visit} · {resp.protocol.name}</div>
        {fields.length === 0 && <p className="muted small">No approved or draft fields for this visit.</p>}
        <div className="entry-grid">
          {fields.flatMap((f) =>
            Array.from({ length: Math.max(1, f.repeats) }, (_, i) => {
              const rep = i + 1;
              const k = slot(f.name, rep);
              const err = errorFor(k);
              const label = f.repeats > 1 ? `${f.name} · Reading ${rep}` : f.name;
              const hint = [f.unit, f.min !== null || f.max !== null ? `${f.min ?? "…"}–${f.max ?? "…"}` : null, f.cdash]
                .filter(Boolean).join(" · ");
              const cls = `input${err ? " input-invalid" : ""}`;
              let control;
              if (f.type === "boolean") {
                control = (
                  <label className="check">
                    <input type="checkbox" checked={values[k] === true} onChange={(e) => set(k, e.target.checked)} />
                    Yes
                  </label>
                );
              } else if (f.type === "choice" && f.choices) {
                control = (
                  <select id={k} className={cls} value={String(values[k] ?? "")} onChange={(e) => set(k, e.target.value)}>
                    <option value="">—</option>
                    {f.choices.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                );
              } else if (f.type === "integer" || f.type === "decimal") {
                control = (
                  <input
                    id={k} className={cls} type="number"
                    min={f.min ?? undefined} max={f.max ?? undefined}
                    step={f.type === "integer" ? 1 : "any"}
                    value={String(values[k] ?? "")} onChange={(e) => set(k, e.target.value)}
                  />
                );
              } else if (f.type === "date") {
                control = <input id={k} className={cls} type="date" value={String(values[k] ?? "")} onChange={(e) => set(k, e.target.value)} />;
              } else {
                control = <input id={k} className={cls} type="text" value={String(values[k] ?? "")} onChange={(e) => set(k, e.target.value)} />;
              }
              return (
                <div className="entry-field" key={k}>
                  <label className="label" htmlFor={k}>
                    {label}{f.required && <span className="req" aria-label="required">*</span>}
                  </label>
                  {control}
                  {hint && <span className="hint">{hint}</span>}
                  {err && <span className="error">{err}</span>}
                </div>
              );
            }),
          )}
        </div>

        <div className="row mt-5">
          <button type="button" className="btn btn-primary" onClick={save} disabled={saving || fields.length === 0}>
            {saving ? "Saving…" : "Save readings"}
          </button>
          {message && <span className={message.kind === "ok" ? "ok" : "error"}>{message.text}</span>}
        </div>
      </div>

      <div className="card mt-4">
        <div className="row row-between row-wrap">
          <p className="strong">On file for {subject}</p>
          <p className="muted small">Ask the sponsor about any value; an approved value can only be changed through a query.</p>
        </div>
        {entered.length === 0 && (
          <p className="muted small mt-2">Nothing saved for this patient yet. Save readings above; each one then appears here with an <em>Ask the sponsor</em> link. You can also start a query from the Queries page.</p>
        )}
        {entered.length > 0 && (
          <table className="table mt-2">
            <thead><tr><th>Visit</th><th>Field</th><th>Value</th><th>Status</th><th /></tr></thead>
            <tbody>
              {entered.map((r) => (
                <tr key={r.id}>
                  <td>{r.visit}</td>
                  <td>{r.field}{r.repeat > 1 ? ` · ${r.repeat}` : ""}</td>
                  <td className="mono">{r.value ?? "—"}</td>
                  <td><span className={`pill ${r.status === "approved" ? "chip-teal" : r.status === "queried" ? "chip-amber" : ""}`}>{r.status}</span></td>
                  <td className="num">
                    {r.status !== "queried" && (
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
            <button type="button" className="btn btn-primary btn-sm" onClick={ask} disabled={askBusy || !asking.text.trim()}>{askBusy ? "Sending…" : "Send query"}</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAsking(null)}>Cancel</button>
          </div>
        )}
      </div>
    </div>
  );
}
