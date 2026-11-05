import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { DraftResponse, SiteRow } from "../api/types";
import { useAuth } from "../auth/useAuth";

/* Which hospitals work on this protocol. Assignment needs a locked form,
   because a site only ever sees the locked version. */
export default function Sites() {
  const id = Number(useParams().id);
  const { can } = useAuth();
  const [draft, setDraft] = useState<DraftResponse | null>(null);
  const [sites, setSites] = useState<SiteRow[] | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [d, s] = await Promise.all([api.draft(id), api.sites(id)]);
      setDraft(d); setSites(s); setError(null);
    } catch (e) { setError((e as Error).message); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const toggle = async (row: SiteRow) => {
    setBusy(row.org_id); setError(null);
    try {
      if (row.assigned) await api.unassignSite(id, row.org_id);
      else await api.assignSite(id, row.org_id);
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  };

  if (!draft && !error) return <div className="page"><p className="muted">Loading…</p></div>;
  const locked = draft?.state === "locked";

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">{draft?.protocol.name ?? "Sites"}</h1>
        <div className="muted small">Sites</div>
        <Link className="btn btn-secondary btn-sm" to={`/sponsor/ecrf-status?protocol=${id}`}>View eCRF status</Link>
      </div>

      {!locked && (
        <div className="card">
          <p className="strong">Lock the form first</p>
          <p className="muted small mt-2">
            A site only ever sees a locked form, so sites can be assigned once the form is locked.{" "}
            <Link className="inline" to={`/sponsor/p/${id}/review`}>Go to Review</Link>
          </p>
        </div>
      )}

      {locked && sites && (
        <div className="card">
          <div className="section-title">Assigned sites</div>
          <p className="muted small mb-3">
            An assigned site sees this study in its portal and can add its own patients and enter their data.
            {!can("site.assign") && " Only sponsor accounts can change assignments."}
          </p>
          {sites.map((s) => (
            <label className="check site-row" key={s.org_id}>
              <input
                type="checkbox" checked={s.assigned}
                disabled={!can("site.assign") || busy !== null}
                onChange={() => toggle(s)}
              />
              <span className="mono">{s.code}</span>
              <span>{s.name}</span>
              {busy === s.org_id && <span className="muted small">saving…</span>}
            </label>
          ))}
        </div>
      )}

      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
