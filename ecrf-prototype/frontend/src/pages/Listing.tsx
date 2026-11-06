import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ListingResponse } from "../api/types";
import { useAuth } from "../auth/useAuth";

/* One form's values across the subjects you may see, one row per subject,
   visit and reading. The status is the row's least advanced value. */
export default function Listing() {
  const params = useParams();
  const id = Number(params.id);
  const form = params.form;
  const navigate = useNavigate();
  const { can } = useAuth();
  const [forms, setForms] = useState<string[]>([]);
  const [d, setD] = useState<ListingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api.listingForms(id).then((r) => {
      setForms(r.forms);
      if (!form && r.forms.length) navigate(`/listing/${id}/${encodeURIComponent(r.forms[0])}`, { replace: true });
    }).catch((e) => setError((e as Error).message));
  }, [id, form, navigate]);

  useEffect(() => {
    if (!form) return;
    setD(null);
    api.listing(id, form).then((r) => { setD(r); setError(null); }).catch((e) => setError((e as Error).message));
  }, [id, form]);

  const exportCsv = async () => {
    if (!form) return;
    setError(null);
    try { await api.listingExport(id, form); setMessage("Exported. The export is on the access log."); }
    catch (e) { setError((e as Error).message); }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Data listing</h1>
        <div className="muted small">One form's values across the subjects you may see.</div>
      </div>
      <div className="row row-wrap row-between filters mb-3">
        <select className="input" aria-label="Form" value={form ?? ""}
                onChange={(e) => navigate(`/listing/${id}/${encodeURIComponent(e.target.value)}`)}>
          {forms.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        {can("listing.export") && <button type="button" className="btn btn-secondary btn-sm" onClick={exportCsv} disabled={!d}>Export CSV</button>}
      </div>
      {message && <p className="ok mb-3">{message}</p>}
      {error && <p className="error mb-3">{error}</p>}
      {d && (
        <div className="card">
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr><th>Subject</th><th>Site</th><th>Visit</th><th className="num">Reading</th><th>Status</th>{d.columns.map((c) => <th key={c}>{c}</th>)}</tr>
              </thead>
              <tbody>
                {d.rows.map((r) => (
                  <tr key={`${r.subject}-${r.visit}-${r.repeat}`}>
                    <td className="mono">{r.subject}</td><td>{r.site}</td><td>{r.visit}</td><td className="num">{r.repeat}</td>
                    <td className="small">{r.status.replace("_", " ")}</td>
                    {d.columns.map((c) => <td key={c}>{r.values[c] ?? ""}</td>)}
                  </tr>
                ))}
                {d.rows.length === 0 && <tr><td colSpan={d.columns.length + 5} className="muted small">Nothing entered on this form yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
