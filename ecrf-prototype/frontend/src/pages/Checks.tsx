import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { DraftResponse, EditCheck } from "../api/types";
import { useAuth } from "../auth/useAuth";

const TYPES = ["required", "range", "format", "cross_field", "cross_form", "temporal", "conditional", "manual"] as const;
type CheckType = (typeof TYPES)[number];
const TYPE_HELP: Record<CheckType, string> = {
  required: "The field must be answered.",
  range: "A number must lie between a minimum and a maximum.",
  format: "The value must match a pattern. The only type that can block a save.",
  cross_field: "Two fields on one form compared.",
  cross_form: "A field at one visit compared with a field at another.",
  temporal: "One date before or after another.",
  conditional: "If one field equals a value, another must be answered.",
  manual: "A check for people to do. It is listed and never run.",
};

/* The edit checks on one protocol. Built-in ones are generated at lock. Before
   the lock a builder manages them; after it, the data manager does, and every
   change is logged. */
export default function Checks() {
  const id = Number(useParams().id);
  const { can } = useAuth();
  const [resp, setResp] = useState<DraftResponse | null>(null);
  const [rows, setRows] = useState<EditCheck[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [type, setType] = useState<CheckType>("range");
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [op, setOp] = useState("<");
  const [lo, setLo] = useState("");
  const [hi, setHi] = useState("");
  const [equals, setEquals] = useState("");
  const [pattern, setPattern] = useState("");
  const [severity, setSeverity] = useState("soft");
  const [text, setText] = useState("");
  const [sampleA, setSampleA] = useState("");
  const [sampleB, setSampleB] = useState("");
  const [tried, setTried] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [d, c] = await Promise.all([api.draft(id), api.checks(id)]);
      setResp(d); setRows(c); setError(null);
    } catch (e) { setError((e as Error).message); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const locked = resp?.state === "locked";
  const mayChange = locked ? can("protocol.lock") : can("form.edit");
  const fields = useMemo(() => (resp?.draft?.forms ?? []).flatMap((f) => f.fields
    .filter((x) => x.status !== "rejected")
    .map((x) => ({ id: x.field_id, visit: f.visit, label: `${f.visit}: ${x.name}` }))), [resp]);
  const nameOf = (fid: string) => fields.find((f) => f.id === fid)?.label ?? fid;
  const two = type === "cross_field" || type === "cross_form" || type === "temporal" || type === "conditional";

  const body = () => {
    const logic: Record<string, unknown> = {};
    if (type === "range") { logic.min = lo === "" ? null : Number(lo); logic.max = hi === "" ? null : Number(hi); }
    if (type === "format") { logic.kind = "pattern"; logic.pattern = pattern; }
    if (type === "cross_field" || type === "cross_form") { logic.a = a; logic.b = b; logic.op = op; }
    if (type === "temporal") { logic.a = a; logic.b = b; logic.op = op; }
    if (type === "conditional") { logic.if_field = a; logic.equals = equals; logic.then_required = [b]; }
    return { type, field_ids: two ? [a, b] : [a], logic };
  };

  const add = async () => {
    setError(null);
    try {
      const visit = fields.find((f) => f.id === a)?.visit;
      await api.addCheck(id, { ...body(), message: text, severity, form: type === "cross_form" ? null : visit ?? null });
      setText(""); setTried(null);
      await load();
    } catch (e) { setError((e as Error).message); }
  };

  const tryIt = async () => {
    setError(null);
    try {
      const sample: Record<string, string> = {};
      if (a) sample[a] = sampleA;
      if (b && two) sample[b] = sampleB;
      const r = await api.testCheck(id, { ...body(), sample });
      setTried(r.passes === null ? "A manual check is never evaluated." : r.passes ? "These values pass." : "These values would fail this check.");
    } catch (e) { setError((e as Error).message); }
  };

  const toggle = async (c: EditCheck) => {
    setError(null);
    try { await api.editCheck(id, c.id, { enabled: !c.enabled }); await load(); }
    catch (e) { setError((e as Error).message); }
  };

  if (!rows && !error) return <div className="page"><p className="muted">Loading…</p></div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Edit checks</h1>
        <div className="muted small">
          A soft check raises a query at submit. A hard check blocks the save. Checks never change what was entered.
          {locked ? " The form is locked, so a change here takes the data manager and is logged." : " Built-in checks are generated when the form is locked."}
        </div>
      </div>

      {mayChange && resp?.draft && (
        <div className="card">
          <div className="section-title">Add a check</div>
          <div className="register">
            <label className="ctl">Type
              <select className="input input-sm" value={type} onChange={(e) => { setType(e.target.value as CheckType); setSeverity("soft"); setTried(null); }}>
                {TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
              </select>
            </label>
            <label className="ctl ctl-wide">{two ? "First field" : "Field"}
              <select className="input input-sm input-grow" value={a} onChange={(e) => setA(e.target.value)}>
                <option value="">—</option>
                {fields.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
              </select>
            </label>
            {two && (
              <label className="ctl ctl-wide">Second field
                <select className="input input-sm input-grow" value={b} onChange={(e) => setB(e.target.value)}>
                  <option value="">—</option>
                  {fields.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
                </select>
              </label>
            )}
            {(type === "cross_field" || type === "cross_form") && (
              <label className="ctl">Must be
                <select className="input input-sm" value={op} onChange={(e) => setOp(e.target.value)}>
                  {["<", "<=", ">", ">=", "==", "!="].map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </label>
            )}
            {type === "temporal" && (
              <label className="ctl">First field must be
                <select className="input input-sm" value={op} onChange={(e) => setOp(e.target.value)}>
                  {["before", "on_or_before", "after", "on_or_after"].map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}
                </select>
              </label>
            )}
            {type === "conditional" && (
              <label className="ctl">If first field equals
                <input className="input input-sm" value={equals} onChange={(e) => setEquals(e.target.value)} placeholder="Yes" />
              </label>
            )}
            {type === "range" && (
              <>
                <label className="ctl">Min<input className="input input-sm input-mono" type="number" value={lo} onChange={(e) => setLo(e.target.value)} /></label>
                <label className="ctl">Max<input className="input input-sm input-mono" type="number" value={hi} onChange={(e) => setHi(e.target.value)} /></label>
              </>
            )}
            {type === "format" && (
              <>
                <label className="ctl ctl-wide">Pattern (regular expression)
                  <input className="input input-sm input-grow input-mono" value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder="V\d+\.\d+" />
                </label>
                <label className="ctl">Severity
                  <select className="input input-sm" value={severity} onChange={(e) => setSeverity(e.target.value)}>
                    <option value="soft">soft</option>
                    <option value="hard">hard</option>
                  </select>
                </label>
              </>
            )}
            <label className="ctl ctl-wide">Message the site sees
              <input className="input input-sm input-grow" value={text} onChange={(e) => setText(e.target.value)} placeholder="Say what to check, without suggesting the answer" />
            </label>
          </div>
          <p className="muted small mt-2">{TYPE_HELP[type]}</p>
          {type !== "manual" && (
            <div className="row row-wrap mt-3">
              <input className="input input-sm" placeholder="Sample value" value={sampleA} onChange={(e) => setSampleA(e.target.value)} aria-label="Sample value for the first field" />
              {two && <input className="input input-sm" placeholder="Second sample" value={sampleB} onChange={(e) => setSampleB(e.target.value)} aria-label="Sample value for the second field" />}
              <button type="button" className="btn btn-secondary btn-sm" onClick={tryIt} disabled={!a}>Try it</button>
              {tried && <span className="small">{tried}</span>}
            </div>
          )}
          <button type="button" className="btn btn-primary btn-sm mt-3" onClick={add} disabled={!a || (two && !b) || !text.trim()}>Add check</button>
        </div>
      )}

      <div className="card">
        <table className="table">
          <thead><tr><th>Code</th><th>Type</th><th>Severity</th><th>Fields</th><th>Message</th><th>On</th></tr></thead>
          <tbody>
            {(rows ?? []).map((c) => (
              <tr key={c.id}>
                <td className="mono">{c.code}</td>
                <td>{c.type.replace("_", " ")}</td>
                <td><span className={`pill ${c.severity === "hard" ? "chip-rust" : ""}`}>{c.severity}</span></td>
                <td className="small">{c.field_ids.map(nameOf).join(", ")}</td>
                <td className="small">{c.message}</td>
                <td>
                  <input type="checkbox" checked={c.enabled} disabled={!mayChange} aria-label={`${c.code} on`} onChange={() => toggle(c)} />
                </td>
              </tr>
            ))}
            {rows && rows.length === 0 && <tr><td colSpan={6} className="muted small">No checks yet. Built-in checks appear when the form is locked.</td></tr>}
          </tbody>
        </table>
      </div>
      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
