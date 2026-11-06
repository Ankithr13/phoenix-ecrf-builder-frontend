import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { SapItem, SapItemIn, SapResponse } from "../api/types";
import { useAuth } from "../auth/useAuth";

const EMPTY: SapItemIn = { label: "", kind: "endpoint", field_id: "", baseline_visit_id: null, analysis_visit_id: null, unit: null, responder_rule: null, method: null };
const WHAT_RUNS: Record<string, string> = {
  endpoint: "Descriptive statistics, change from baseline with a 95% CI and paired t-test, responder rate if a rule is set, missing values.",
  baseline: "Descriptive statistics at the baseline visit, missing values.",
  disposition: "Descriptive statistics at the analysis visit, missing values.",
  safety: "Treatment-emergent adverse events and missing values. Pick the AE start date as the field. The start of treatment is the baseline visit's date if set, otherwise each subject's first visit date.",
};

function ruleText(r: SapItem["responder_rule"]): string {
  return r ? `${r.on === "change" ? "Change" : "Analysis value"} ${r.op} ${r.value}` : "—";
}

/* Mirrors the client's traceability matrix: endpoint, form field, visits, unit,
   derivation, method. A row picks what the fixed calculations work on. It can
   add no calculation of its own. */
export default function Sap() {
  const id = Number(useParams().id);
  const { can } = useAuth();
  const editable = can("sap.edit");
  const [d, setD] = useState<SapResponse | null>(null);
  const [form, setForm] = useState<SapItemIn | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  // Text while it is being typed: a number input cannot hold a lone minus sign.
  const [threshold, setThreshold] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setD(await api.sap(id)); setError(null); }
    catch (e) { setError((e as Error).message); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  // The same field at another visit is the same thing to the plan.
  const fields = useMemo(() => {
    const seen = new Map<string, SapResponse["fields"][number]>();
    for (const f of d?.fields ?? []) if (!seen.has(f.name)) seen.set(f.name, f);
    return Array.from(seen.values());
  }, [d]);

  const set = (patch: Partial<SapItemIn>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const edit = (i: SapItem) => {
    setEditing(i.id);
    setForm({ label: i.label, kind: i.kind, field_id: fields.find((f) => f.name === i.field)?.field_id ?? i.field_id,
              baseline_visit_id: i.baseline_visit_id, analysis_visit_id: i.analysis_visit_id, unit: i.unit,
              responder_rule: i.responder_rule, method: i.method });
    setThreshold(i.responder_rule ? String(i.responder_rule.value) : "");
  };
  const pickField = (fieldId: string) => {
    const f = fields.find((x) => x.field_id === fieldId);
    set({ field_id: fieldId, unit: form?.unit || f?.unit || null });
  };
  const message = (e: unknown) => (e instanceof ApiError && typeof e.detail === "string" ? e.detail : (e as Error).message);
  const save = async () => {
    if (!form) return;
    setError(null);
    try {
      const body = form.responder_rule ? { ...form, responder_rule: { ...form.responder_rule, value: Number(threshold) } } : form;
      if (editing) await api.sapUpdate(id, editing, body); else await api.sapAdd(id, body);
      setForm(null); setEditing(null);
      await load();
    } catch (e) { setError(message(e)); }
  };
  const remove = async (i: SapItem) => {
    if (!window.confirm(`Remove "${i.label}" from the plan?`)) return;
    setError(null);
    try { await api.sapDelete(id, i.id); await load(); }
    catch (e) { setError(message(e)); }
  };

  if (!d) return <div className="page">{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</div>;
  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Statistical analysis plan</h1>
        <div className="muted small">Each row tells the fixed calculations what to work on. Results appear on the Dashboard, computed on approved values only.</div>
      </div>
      <div className="card">
        <div className="table-scroll">
          <table className="table">
            <thead><tr><th>Label</th><th>Kind</th><th>Field</th><th>Baseline visit</th><th>Analysis visit</th><th>Unit</th><th>Responder rule</th><th>Method</th><th /></tr></thead>
            <tbody>
              {d.items.map((i) => (
                <tr key={i.id}>
                  <td className="strong">{i.label}</td><td>{i.kind}</td>
                  <td>{i.field ?? <span className="error">not on the form</span>}</td>
                  <td>{i.baseline_visit_id ?? "—"}</td><td>{i.analysis_visit_id ?? "—"}</td><td>{i.unit ?? "—"}</td>
                  <td className="mono small">{ruleText(i.responder_rule)}</td><td className="small">{i.method ?? "—"}</td>
                  <td className="num">
                    {editable && (
                      <>
                        <button type="button" className="btn-link small" onClick={() => edit(i)}>Edit</button>{" "}
                        <button type="button" className="btn-link small" onClick={() => remove(i)}>Remove</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {d.items.length === 0 && <tr><td colSpan={9} className="muted small">Nothing in the plan yet.</td></tr>}
            </tbody>
          </table>
        </div>
        {editable && !form && (
          <button type="button" className="btn btn-secondary btn-sm mt-3" onClick={() => { setEditing(null); setForm(EMPTY); }}>Add a row</button>
        )}
      </div>

      {form && (
        <div className="card mt-4">
          <div className="section-title">{editing ? "Edit row" : "New row"}</div>
          <div className="grid-2">
            <label className="field-label">Label
              <input className="input" value={form.label} onChange={(e) => set({ label: e.target.value })} />
            </label>
            <label className="field-label">Kind
              <select className="input" value={form.kind} onChange={(e) => set({ kind: e.target.value, responder_rule: e.target.value === "endpoint" ? form.responder_rule : null })}>
                {d.kinds.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </label>
            <label className="field-label">Field
              <select className="input" value={form.field_id} onChange={(e) => pickField(e.target.value)}>
                <option value="">Choose a field</option>
                {fields.map((f) => <option key={f.field_id} value={f.field_id}>{f.name}</option>)}
              </select>
            </label>
            <label className="field-label">Unit
              <input className="input" value={form.unit ?? ""} onChange={(e) => set({ unit: e.target.value || null })} />
            </label>
            <label className="field-label">Baseline visit
              <select className="input" value={form.baseline_visit_id ?? ""} onChange={(e) => set({ baseline_visit_id: e.target.value || null })}>
                <option value="">None</option>
                {d.visits.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </label>
            <label className="field-label">Analysis visit
              <select className="input" value={form.analysis_visit_id ?? ""} onChange={(e) => set({ analysis_visit_id: e.target.value || null })}>
                <option value="">None</option>
                {d.visits.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </label>
          </div>
          {form.kind === "endpoint" && (
            <div className="mt-3">
              <label className="row row-wrap small">
                <input type="checkbox" checked={!!form.responder_rule}
                       onChange={(e) => { setThreshold(""); set({ responder_rule: e.target.checked ? { on: "change", op: d.operators[0], value: 0 } : null }); }} />
                A responder is a subject whose
                {form.responder_rule && (
                  <>
                    <select className="input" aria-label="Rule tests" value={form.responder_rule.on}
                            onChange={(e) => set({ responder_rule: { ...form.responder_rule!, on: e.target.value as "change" | "analysis" } })}>
                      <option value="change">change from baseline</option>
                      <option value="analysis">analysis value</option>
                    </select>
                    <select className="input" aria-label="Rule operator" value={form.responder_rule.op}
                            onChange={(e) => set({ responder_rule: { ...form.responder_rule!, op: e.target.value } })}>
                      {d.operators.map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                    <input className="input input-sm" inputMode="decimal" aria-label="Rule threshold" value={threshold}
                           onChange={(e) => setThreshold(e.target.value)} />
                  </>
                )}
              </label>
            </div>
          )}
          <label className="field-label mt-3">Method, as the plan states it
            <input className="input" value={form.method ?? ""} onChange={(e) => set({ method: e.target.value || null })} />
          </label>
          <p className="muted small mt-3">What this kind computes: {WHAT_RUNS[form.kind]}</p>
          <div className="row mt-3">
            <button type="button" className="btn btn-primary btn-sm" onClick={save}
                    disabled={!form.label.trim() || !form.field_id || (!!form.responder_rule && !Number.isFinite(parseFloat(threshold)))}>Save</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setForm(null); setEditing(null); }}>Cancel</button>
          </div>
        </div>
      )}
      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
