import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { NotificationRow } from "../api/types";

const KIND_LABEL: Record<string, string> = {
  query_raised: "Query raised", query_answered: "Query answered", system_query: "System query",
  visit_submitted: "Visit submitted", visit_approved: "Visit approved", signoff_needed: "Sign-off needed",
  signoff_invalidated: "Sign-off undone", form_locked: "Form locked", study_locked: "Study locked",
};

/* Unread first. In the app only: nothing here sends an email. On a protocol's
   own page, the route's id narrows it to that protocol. */
export default function Notifications() {
  const params = useParams();
  const scoped = params.id ? Number(params.id) : null;
  const [rows, setRows] = useState<NotificationRow[] | null>(null);
  const [protocol, setProtocol] = useState("");
  const [kind, setKind] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await api.notifications({ protocol_id: scoped ? String(scoped) : protocol, kind }));
      setError(null);
    } catch (e) { setError((e as Error).message); }
  }, [scoped, protocol, kind]);
  useEffect(() => { load(); }, [load]);

  const protocols = useMemo(() => {
    const m = new Map<number, string>();
    for (const n of rows ?? []) m.set(n.protocol_id, n.protocol_name ?? String(n.protocol_id));
    return Array.from(m);
  }, [rows]);
  const unread = (rows ?? []).filter((n) => !n.read_at).length;

  const act = async (fn: () => Promise<unknown>) => {
    try { await fn(); await load(); window.dispatchEvent(new Event("notifications-changed")); }
    catch (e) { setError((e as Error).message); }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Notifications</h1>
        <div className="muted small">{unread} unread. Shown here only; nothing is emailed.</div>
      </div>
      <div className="row row-wrap filters mb-3">
        {!scoped && (
          <select className="input" value={protocol} onChange={(e) => setProtocol(e.target.value)} aria-label="Protocol">
            <option value="">All protocols</option>
            {protocols.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        )}
        <select className="input" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind">
          <option value="">All kinds</option>
          {Object.entries(KIND_LABEL).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
        <span className="grow" />
        <button type="button" className="btn btn-secondary btn-sm" disabled={unread === 0}
                onClick={() => act(() => api.readAllNotifications(scoped ?? undefined))}>Mark all read</button>
      </div>
      {rows && rows.length === 0 && <div className="card"><p className="muted small">Nothing here.</p></div>}
      {(rows ?? []).map((n) => (
        <div className={`card notification${n.read_at ? " read" : ""}`} key={n.id}>
          <div className="row row-between row-wrap">
            <div className="row row-wrap">
              <span className="pill">{KIND_LABEL[n.kind] ?? n.kind}</span>
              {n.subject && <span className="mono small">{n.subject}</span>}
              {n.visit && <span className="small">{n.visit}</span>}
            </div>
            <div className="small muted">{n.protocol_name} · {new Date(n.created_at).toLocaleString()}</div>
          </div>
          <div className="row row-between mt-2">
            <div className="small">{n.body}</div>
            {!n.read_at && <button type="button" className="btn-link small" onClick={() => act(() => api.readNotification(n.id))}>Mark read</button>}
          </div>
        </div>
      ))}
      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
