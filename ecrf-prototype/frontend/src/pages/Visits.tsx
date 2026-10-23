import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Plan } from "../api/types";
import { useAuth } from "../auth/useAuth";

/* The one human step in extraction. Pass one proposes the visit list; a
   person fixes it here; pass two is paid for only once it is confirmed.
   The same PDF once came back with 18 visits and then 8, and every visit
   is a paid call, so this page is where the money is saved. */
export default function Visits() {
  const id = Number(useParams().id);
  const { can } = useAuth();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [name, setName] = useState("");
  const [visits, setVisits] = useState<string[]>([]);
  const [busy, setBusy] = useState<"visits" | "save" | "fields" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsForce, setNeedsForce] = useState(false);
  const [newVisit, setNewVisit] = useState("");

  const load = useCallback(async () => {
    try {
      const [d, p] = await Promise.all([api.draft(id), api.visits(id)]);
      setName(d.protocol.name);
      setPlan(p);
      setVisits(p.visits);
      setError(null);
    } catch (e) { setError((e as Error).message); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const fail = (e: unknown) => {
    const err = e as ApiError;
    setError(err.message);
    setNeedsForce(err instanceof ApiError && err.status === 409 && String(err.detail).includes("force=true"));
  };

  const findVisits = async (force = false) => {
    setBusy("visits"); setError(null); setNeedsForce(false);
    try { const p = await api.extractVisits(id, force); setPlan(p); setVisits(p.visits); }
    catch (e) { fail(e); }
    finally { setBusy(null); }
  };

  const save = async () => {
    setBusy("save"); setError(null);
    try { const p = await api.saveVisits(id, visits); setPlan(p); setVisits(p.visits); }
    catch (e) { fail(e); }
    finally { setBusy(null); }
  };

  const confirmAndExtract = async (force = false) => {
    setBusy("fields"); setError(null); setNeedsForce(false);
    try {
      const p = await api.saveVisits(id, visits);
      setPlan(p);
      await api.extractFields(id, force);
      navigate(`/sponsor/p/${id}/review`);
    } catch (e) { fail(e); }
    finally { setBusy(null); }
  };

  const move = (i: number, d: -1 | 1) => setVisits((v) => {
    const j = i + d; if (j < 0 || j >= v.length) return v;
    const n = [...v]; [n[i], n[j]] = [n[j], n[i]]; return n;
  });
  const rename = (i: number, val: string) => setVisits((v) => v.map((x, k) => (k === i ? val : x)));
  const remove = (i: number) => setVisits((v) => v.filter((_, k) => k !== i));
  const add = () => {
    const v = newVisit.trim();
    if (!v || visits.includes(v)) return;
    setVisits((prev) => [...prev, v]); setNewVisit("");
  };

  const dirty = plan ? JSON.stringify(plan.visits) !== JSON.stringify(visits) : false;
  const dupes = new Set(visits).size !== visits.length;
  const perForm = plan?.strategy === "per_form" && plan.forms.length > 0;
  const calls = perForm ? plan!.forms.length : visits.length;
  const usage = plan?.usage;

  if (!plan && !error) return <div className="page"><p className="muted">Loading…</p></div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">{name || "Visits"}</h1>
        <div className="muted small">Confirm the visit list before the per-visit calls are paid for</div>
      </div>

      {plan && plan.visits.length === 0 && (
        <div className="card">
          <p className="strong">No visit list yet</p>
          <p className="muted small mt-2">
            The first call reads the whole protocol and proposes the study visits. Nothing else is sent until you confirm them.
          </p>
          {can("protocol.extract") && (
            <button type="button" className="btn btn-primary mt-4" onClick={() => findVisits(false)} disabled={busy !== null}>
              {busy === "visits" ? "Reading the protocol…" : "Find visits"}
            </button>
          )}
        </div>
      )}

      {plan && plan.visits.length > 0 && (
        <>
          <div className="grid-3">
            <div className="stat">
              <div className="stat-label">Visits</div>
              <div className="stat-value">{visits.length}</div>
              <div className="stat-sub">{plan.confirmed ? "confirmed" : "proposed by the model, not yet confirmed"}</div>
            </div>
            <div className="stat">
              <div className="stat-label">Calls to extract fields</div>
              <div className="stat-value">{calls}</div>
              <div className="stat-sub">{perForm ? `one per form, ${plan.forms.length} forms` : "one per visit"} · strategy {plan.strategy}</div>
            </div>
            <div className="stat">
              <div className="stat-label">Pass one so far</div>
              <div className="stat-value">{usage ? `$${usage.est_cost_usd.toFixed(4)}` : "—"}</div>
              <div className="stat-sub">
                {usage ? `${usage.llm_calls_made} call${usage.llm_calls_made === 1 ? "" : "s"}${usage.llm_calls_from_cache ? `, ${usage.llm_calls_from_cache} from cache` : ""} · ${usage.input_tokens.toLocaleString()} in · ${usage.output_tokens.toLocaleString()} out` : ""}
              </div>
            </div>
          </div>

          <div className="card mt-4">
            <div className="section-title">Visit list</div>
            <p className="muted small mb-3">Rename, reorder, remove or add visits. Each visit becomes one form and, with the per-visit strategy, one call.</p>
            <ol className="visit-list">
              {visits.map((v, i) => (
                <li className="visit-row" key={i}>
                  <span className="mono muted small visit-num">{i + 1}</span>
                  <input className="input" value={v} onChange={(e) => rename(i, e.target.value)} disabled={!can("protocol.extract")} aria-label={`Visit ${i + 1} name`} />
                  {can("protocol.extract") && (
                    <span className="row">
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move up">↑</button>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => move(i, 1)} disabled={i === visits.length - 1} aria-label="Move down">↓</button>
                      <button type="button" className="btn btn-danger btn-sm" onClick={() => remove(i)} aria-label="Remove visit">Remove</button>
                    </span>
                  )}
                </li>
              ))}
            </ol>
            {can("protocol.extract") && (
              <div className="row mt-3">
                <input className="input" placeholder="Add a visit, e.g. Week 8" value={newVisit} onChange={(e) => setNewVisit(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
                <button type="button" className="btn btn-secondary" onClick={add} disabled={!newVisit.trim()}>Add</button>
              </div>
            )}
            {dupes && <p className="error mt-2">Visit names must be unique.</p>}
          </div>

          {perForm && (
            <details className="panel mt-4">
              <summary>Forms the model found <span className="mono muted-2">{plan.forms.length}</span></summary>
              <div className="panel-body">
                <table className="table">
                  <thead><tr><th>Form</th><th>Collected at</th></tr></thead>
                  <tbody>
                    {plan.forms.map((f) => <tr key={f.name}><td>{f.name}</td><td className="small muted">{f.visits.join(", ")}</td></tr>)}
                  </tbody>
                </table>
              </div>
            </details>
          )}

          {can("protocol.extract") && (
            <div className="row row-wrap mt-4">
              <button type="button" className="btn btn-primary" onClick={() => confirmAndExtract(false)} disabled={busy !== null || visits.length === 0 || dupes}>
                {busy === "fields" ? `Extracting fields, ${calls} calls…` : `Confirm and extract fields (${calls} call${calls === 1 ? "" : "s"})`}
              </button>
              <button type="button" className="btn btn-secondary" onClick={save} disabled={busy !== null || !dirty || dupes}>
                {busy === "save" ? "Saving…" : "Save list"}
              </button>
              <button type="button" className="btn-link" onClick={() => findVisits(false)} disabled={busy !== null}>ask the model again</button>
              <span className="grow" />
              <Link className="small muted" to={`/sponsor/p/${id}/review`}>Review →</Link>
            </div>
          )}
        </>
      )}

      {error && (
        <div className="card card-rust mt-4">
          <p className="small">{error}</p>
          {needsForce && can("protocol.extract") && (
            <button type="button" className="btn btn-danger btn-sm mt-3" onClick={() => (plan && plan.visits.length ? confirmAndExtract(true) : findVisits(true))} disabled={busy !== null}>
              Extract anyway, as a new version
            </button>
          )}
        </div>
      )}
    </div>
  );
}
