import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { SubjectRow } from "../api/types";
import { useAuth } from "../auth/useAuth";

/* A site's patients on one study. The code is made by the server, so a
   site cannot type its way into another site's patient. */
export default function Patients() {
  const id = Number(useParams().id);
  const { can, me } = useAuth();
  const [rows, setRows] = useState<SubjectRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setRows(await api.subjects(id)); setError(null); }
    catch (e) { setError((e as Error).message); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    setBusy(true); setError(null);
    try { await api.createSubject(id); await load(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  if (!rows && !error) return <div className="page"><p className="muted">Loading…</p></div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Patients</h1>
        <div className="muted small">{me?.org.name} · codes start with {me?.org.code}-</div>
      </div>

      <div className="card">
        <div className="row row-between row-wrap">
          <p className="muted small">Synthetic data only. No real patient information is entered into this prototype.</p>
          {can("subject.create") && (
            <button type="button" className="btn btn-primary" onClick={add} disabled={busy}>
              {busy ? "Adding…" : "Add patient"}
            </button>
          )}
        </div>
      </div>

      {rows && rows.length === 0 && (
        <div className="card"><p className="muted small">No patients yet. Add one to start entering data.</p></div>
      )}
      {rows && rows.length > 0 && (
        <div className="card">
          <table className="table">
            <thead><tr><th>Patient</th><th className="num">Readings</th><th>Added</th><th /></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono strong">{r.code}</td>
                  <td className="num mono">{r.readings}</td>
                  <td className="small muted">{new Date(r.created_at).toLocaleDateString()} · {r.created_by}</td>
                  <td className="num"><Link className="btn btn-secondary btn-sm" to={`/site/s/${id}/patients/${encodeURIComponent(r.code)}`}>Enter data</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
