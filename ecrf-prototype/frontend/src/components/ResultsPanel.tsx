import { useMemo, useState } from "react";
import { ApiError, api } from "../api/client";
import type { ResponderRule, SapItem, SapItemIn, SapResponse, Traceability } from "../api/types";

type Field = SapResponse["fields"][number];

const message = (e: unknown) => (e instanceof ApiError && typeof e.detail === "string" ? e.detail : (e as Error).message);

/* A responder rule as the form shows it: a drop or a rise of at least N. */
function ruleParts(r: ResponderRule | null): { dir: "drop" | "rise"; amount: string } {
  if (!r) return { dir: "drop", amount: "" };
  return { dir: r.op.startsWith("<") ? "drop" : "rise", amount: String(Math.abs(r.value)) };
}

function toRule(dir: "drop" | "rise", amount: string): ResponderRule {
  const n = Math.abs(parseFloat(amount));
  return dir === "drop" ? { on: "change", op: "<=", value: -n } : { on: "change", op: ">=", value: n };
}

const ONE_VISIT = new Set(["descriptive", "frequency"]);

/* Add or edit a result. Four choices; the server fills in everything else. */
export function ResultForm({ id, plan, item, onDone, onCancel }: {
  id: number; plan: SapResponse; item?: SapItem; onDone: () => void; onCancel: () => void;
}) {
  // The same field at another visit is the same thing to a result.
  const fields = useMemo(() => {
    const seen = new Map<string, Field>();
    for (const f of plan.fields) if (!seen.has(f.name)) seen.set(f.name, f);
    return Array.from(seen.values());
  }, [plan]);
  const start = item ? fields.find((f) => f.name === item.field) : undefined;
  const [fieldId, setFieldId] = useState(start?.field_id ?? "");
  const [calc, setCalc] = useState(item?.calculation ?? "");
  const [before, setBefore] = useState(item?.baseline_visit_id ?? "");
  const [after, setAfter] = useState(item?.analysis_visit_id ?? "");
  const [rule, setRule] = useState(ruleParts(item?.responder_rule ?? null));
  const [concept, setConcept] = useState(item?.endpoint_concept ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const field = fields.find((f) => f.field_id === fieldId);
  const fits = plan.calculations.filter((c) => field && c.types.includes(field.type));
  const chosen = plan.calculations.find((c) => c.name === calc);
  // Visits where this field is collected.
  const visits = field ? plan.visits.filter((v) => plan.fields.some((f) => f.name === field.name && f.visit === v)) : [];
  const safety = calc === "teae_count";
  const oneVisit = ONE_VISIT.has(calc);
  const visitsOk = safety || (oneVisit ? (before !== "") !== (after !== "") : before !== "" && after !== "" && before !== after);
  const ruleOk = calc !== "responder_rate" || Number.isFinite(parseFloat(rule.amount));
  const ok = !!field && !!chosen && visitsOk && ruleOk && !busy;

  const pickField = (next: string) => {
    setFieldId(next);
    const f = fields.find((x) => x.field_id === next);
    if (f && chosen && !chosen.types.includes(f.type)) setCalc("");
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    const body: SapItemIn = {
      field_id: fieldId, calculation: calc,
      baseline_visit_id: before || null, analysis_visit_id: safety ? null : after || null,
      responder_rule: calc === "responder_rate" ? toRule(rule.dir, rule.amount) : null,
      endpoint_concept: concept.trim() || null,
    };
    try {
      if (item) await api.sapUpdate(id, item.id, body); else await api.sapAdd(id, body);
      onDone();
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="card mt-4">
      <div className="section-title">{item ? `Edit ${item.label}` : "Add result"}</div>
      <div className="grid-2">
        <label className="field-label">Field
          <select className="input" value={fieldId} onChange={(e) => pickField(e.target.value)}>
            <option value="">Choose a field</option>
            {fields.map((f) => <option key={f.field_id} value={f.field_id}>{f.name}</option>)}
          </select>
        </label>
        <label className="field-label">Calculation
          <select className="input" value={calc} onChange={(e) => setCalc(e.target.value)} disabled={!field}>
            <option value="">{field ? "Choose a calculation" : "Choose a field first"}</option>
            {fits.map((c) => <option key={c.name} value={c.name}>{c.label}</option>)}
          </select>
        </label>
        <label className="field-label">{safety ? "Start of treatment (optional)" : "Before visit (baseline)"}
          <select className="input" value={before} onChange={(e) => setBefore(e.target.value)}>
            <option value="">{safety ? "Each subject's first visit" : "None"}</option>
            {(safety ? plan.visits : visits).map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
        {!safety && (
          <label className="field-label">After visit (analysis)
            <select className="input" value={after} onChange={(e) => setAfter(e.target.value)}>
              <option value="">None</option>
              {visits.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
        )}
      </div>
      {calc === "responder_rate" && (
        <div className="row row-wrap small mt-3">
          A responder is a subject with a
          <select className="input input-sm" aria-label="Drop or rise" value={rule.dir}
                  onChange={(e) => setRule({ ...rule, dir: e.target.value as "drop" | "rise" })}>
            <option value="drop">drop</option>
            <option value="rise">rise</option>
          </select>
          of
          <input className="input input-sm" inputMode="decimal" aria-label="Amount" value={rule.amount}
                 onChange={(e) => setRule({ ...rule, amount: e.target.value })} />
          or more from the before visit to the after visit.
        </div>
      )}
      <label className="field-label mt-3">Endpoint / concept (optional)
        <input className="input" value={concept} onChange={(e) => setConcept(e.target.value)}
               placeholder={field && chosen ? `${field.name} ${chosen.label.toLowerCase()}` : "Filled in from the field and calculation"} />
      </label>
      <p className="muted small mt-3">
        {oneVisit && "A summary is at one visit: pick the before visit or the after visit. "}
        {chosen && `${chosen.label}: ${chosen.formula}. `}
        The SAP item, form, unit, derivation and method are filled in for you. Missing values come with every result.
      </p>
      <div className="row mt-3">
        <button type="button" className="btn btn-primary btn-sm" onClick={save} disabled={!ok}>Save</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
      </div>
      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}

/* The client's eCRF-to-SAP traceability matrix, read only. The columns come
   from the server, so the page and the PDF cannot disagree. */
export function TraceabilityMatrix({ id, m, onClose }: { id: number; m: Traceability; onClose: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const pdf = async () => {
    setError(null);
    try { await api.traceabilityPdf(id); } catch (e) { setError((e as Error).message); }
  };
  return (
    <div className="card mt-4">
      <div className="row row-between row-wrap">
        <div>
          <div className="section-title">Traceability matrix</div>
          <div className="muted small">Form version {m.version} ({m.locked ? "locked" : "draft"}). One row per result.</div>
        </div>
        <div className="row">
          <button type="button" className="btn btn-secondary btn-sm" onClick={pdf}>Download PDF</button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>Close</button>
        </div>
      </div>
      <div className="table-scroll mt-3">
        <table className="table">
          <thead><tr>{m.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>
            {m.rows.map((r, n) => (
              <tr key={n}>{r.map((cell, k) => <td key={k} className={k >= 6 ? "small" : undefined}>{cell || "—"}</td>)}</tr>
            ))}
            {m.rows.length === 0 && <tr><td colSpan={m.columns.length} className="muted small">No results yet.</td></tr>}
          </tbody>
        </table>
      </div>
      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
