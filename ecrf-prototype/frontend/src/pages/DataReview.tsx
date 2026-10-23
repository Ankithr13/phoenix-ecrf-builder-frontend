import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { DataRow, ObservationStatus } from "../api/types";
import { useAuth } from "../auth/useAuth";

const STATUS_CHIP: Record<ObservationStatus, string> = {
  entered: "chip-amber", approved: "chip-teal", queried: "chip-rust",
};

/* The sponsor's view of everything sites have entered. Approving moves a
   value into the statistics; until then it is a submission, not data. */
export default function DataReview() {
  const id = Number(useParams().id);
  const { can } = useAuth();
  const [rows, setRows] = useState<DataRow[] | null>(null);
  const [site, setSite] = useState("");
  const [visit, setVisit] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [asking, setAsking] = useState<{ id: number; text: string } | null>(null);

  const load = useCallback(async () => {
    try { setRows(await api.dataRows(id)); setError(null); }
    catch (e) { setError((e as Error).message); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const sites = useMemo(() => Array.from(new Set((rows ?? []).map((r) => r.site ?? ""))).filter(Boolean).sort(), [rows]);
  const visits = useMemo(() => Array.from(new Set((rows ?? []).map((r) => r.visit))), [rows]);
  const shown = useMemo(() => (rows ?? []).filter((r) =>
    (!site || r.site === site) && (!visit || r.visit === visit) && (!status || r.status === status)), [rows, site, visit, status]);
  const counts = useMemo(() => {
    const c = { entered: 0, approved: 0, queried: 0 };
    for (const r of rows ?? []) c[r.status] += 1;
    return c;
  }, [rows]);

  const toggle = (rid: number) => setSelected((prev) => {
    const n = new Set(prev); if (n.has(rid)) n.delete(rid); else n.add(rid); return n;
  });
  const selectable = shown.filter((r) => r.status === "entered");
  const allSelected = selectable.length > 0 && selectable.every((r) => selected.has(r.id));
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(selectable.map((r) => r.id)));

  const approve = async () => {
    setBusy(true); setError(null); setMessage(null);
    try {
      const r = await api.approveData(id, Array.from(selected));
      setMessage(`${r.approved} value${r.approved === 1 ? "" : "s"} approved`);
      setSelected(new Set());
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const raise_ = async () => {
    if (!asking || !asking.text.trim()) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      await api.raiseQuery(asking.id, asking.text.trim());
      setMessage("Query raised; the site will see it in its portal");
      setAsking(null);
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const seed = async () => {
    setBusy(true); setError(null);
    try { await api.seed(id); await load(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  if (!rows && !error) return <div className="page"><p className="muted">Loading…</p></div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Data review</h1>
        <div className="muted small">
          <span className="mono">{counts.approved}</span> approved · <span className="mono">{counts.entered}</span> awaiting review
          {counts.queried > 0 && <> · <span className="mono">{counts.queried}</span> queried</>}
        </div>
      </div>

      {rows && rows.length === 0 && (
        <div className="card">
          <p className="strong">Nothing entered yet</p>
          <p className="muted small mt-2">Sites enter data through their own portal once the form is locked and they are assigned.</p>
          {can("data.seed") && (
            <button type="button" className="btn btn-secondary btn-sm mt-3" onClick={seed} disabled={busy}>
              {busy ? "Seeding…" : "Seed 20 synthetic subjects"}
            </button>
          )}
        </div>
      )}

      {rows && rows.length > 0 && (
        <div className="card">
          <div className="row row-wrap filters mb-3">
            <select className="input" value={site} onChange={(e) => setSite(e.target.value)} aria-label="Site">
              <option value="">All sites</option>
              {sites.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select className="input" value={visit} onChange={(e) => setVisit(e.target.value)} aria-label="Visit">
              <option value="">All visits</option>
              {visits.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <select className="input" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
              <option value="">All statuses</option>
              <option value="entered">Awaiting review</option>
              <option value="approved">Approved</option>
              <option value="queried">Queried</option>
            </select>
            <span className="grow" />
            {can("data.approve") && (
              <button type="button" className="btn btn-teal btn-sm" onClick={approve} disabled={busy || selected.size === 0}>
                {busy ? "Approving…" : `Approve selected (${selected.size})`}
              </button>
            )}
          </div>

          <table className="table">
            <thead>
              <tr>
                {can("data.approve") && (
                  <th className="chk"><input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all awaiting review" /></th>
                )}
                <th>Site</th><th>Subject</th><th>Visit</th><th>Field</th><th className="num">Value</th><th>Status</th><th>Entered by</th>{can("query.raise") && <th />}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  {can("data.approve") && (
                    <td className="chk">
                      {r.status === "entered" && (
                        <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} aria-label={`Select ${r.field} for ${r.subject}`} />
                      )}
                    </td>
                  )}
                  <td className="mono">{r.site ?? "—"}</td>
                  <td className="mono">{r.subject}</td>
                  <td>{r.visit}</td>
                  <td>{r.field}{r.repeat > 1 ? <span className="muted"> · {r.repeat}</span> : null}</td>
                  <td className="num mono">{r.value ?? "—"}</td>
                  <td><span className={`pill ${STATUS_CHIP[r.status]}`}>{r.status === "entered" ? "awaiting review" : r.status}</span></td>
                  <td className="small muted">{r.entered_by}</td>
                  {can("query.raise") && (
                    <td className="num">
                      {r.status !== "queried" && (
                        <button type="button" className="btn-link" onClick={() => setAsking({ id: r.id, text: "" })}>Raise query</button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
              {shown.length === 0 && <tr><td colSpan={9} className="muted small">No rows match these filters.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {asking && (
        <div className="card card-amber mt-4">
          <div className="section-title">Raise a query</div>
          {(() => { const r = rows?.find((x) => x.id === asking.id); return r ? (
            <p className="small mb-3"><span className="mono">{r.subject}</span> · {r.visit} · <span className="strong">{r.field}</span> = <span className="mono">{r.value ?? "—"}</span></p>
          ) : null; })()}
          <div className="row row-wrap">
            <input className="input grow" placeholder="What should the site check or explain?" value={asking.text} onChange={(e) => setAsking({ ...asking, text: e.target.value })} autoFocus />
            <button type="button" className="btn btn-primary btn-sm" onClick={raise_} disabled={busy || !asking.text.trim()}>Send to site</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAsking(null)}>Cancel</button>
          </div>
        </div>
      )}

      {message && <p className="ok mt-3">{message}</p>}
      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
