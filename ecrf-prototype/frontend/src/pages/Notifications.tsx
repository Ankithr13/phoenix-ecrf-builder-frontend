import { useEffect, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { NotificationRow } from "../api/types";
import { useAuth } from "../auth/useAuth";
import Icon from "../components/Icon";
import NavigationActions from "../components/NavigationActions";
import "../styles/workspace.css";
import "../styles/notifications.css";

const KIND_LABEL: Record<string, string> = {
  query_raised: "Query raised", query_answered: "Query answered", system_query: "System query",
  visit_submitted: "Visit submitted", visit_approved: "Visit approved", signoff_needed: "Sign-off needed",
  signoff_invalidated: "Sign-off undone", form_locked: "Form locked", study_locked: "Study locked",
};

export default function Notifications() {
  const { can } = useAuth();
  if (!can("notifications.view")) return <Navigate to="/" replace />;
  return <Inbox />;
}

function Inbox() {
  const { me, can } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const protocol = params.get("protocol") ?? "";
  const kind = params.get("kind") ?? "";
  const unreadOnly = params.get("unread") === "1";
  const [attempt, setAttempt] = useState(0);
  const [limit, setLimit] = useState(25);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const key = JSON.stringify([me?.user.id, protocol, kind, attempt]);
  const [result, setResult] = useState<{ key: string; rows: NotificationRow[]; error: string | null } | null>(null);
  const [seen, setSeen] = useState<Map<number, string>>(new Map());
  useEffect(() => {
    let active = true;
    api.notifications({ protocol_id: protocol, kind }).then((rows) => {
      if (!active) return;
      setResult({ key, rows, error: null });
      setSeen((previous) => { const next = new Map(previous); rows.forEach((row) => next.set(row.protocol_id, row.protocol_name ?? String(row.protocol_id))); return next; });
    }).catch(() => { if (active) setResult({ key, rows: [], error: "Could not load notifications. Try refreshing the inbox." }); });
    return () => { active = false; };
  }, [key, protocol, kind]);
  const current = result?.key === key ? result : null;
  const rows = current?.rows ?? [];
  const loading = !current;
  const unread = rows.filter((row) => !row.read_at).length;
  const filtered = unreadOnly ? rows.filter((row) => !row.read_at) : rows;
  const visible = filtered.slice(0, limit);
  const error = actionError ?? current?.error;
  const refresh = () => { setActionError(null); setAttempt((previous) => previous + 1); };
  const updateFilter = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value); else next.delete(name);
    setLimit(25); setActionError(null); setParams(next, { replace: true });
  };
  const act = async (operation: () => Promise<unknown>, destination?: string) => {
    if (busy) return;
    setBusy(true); setActionError(null);
    try {
      await operation();
      window.dispatchEvent(new Event("notifications-changed"));
      if (destination) navigate(destination); else refresh();
    } catch { setActionError("Could not update this notification. Your unread status may be unchanged. Please retry."); }
    finally { setBusy(false); }
  };
  const destination = (row: NotificationRow) => {
    const sponsor = me?.org.type === "sponsor";
    if (row.kind.includes("query") && (can("query.raise") || can("query.answer") || can("query.close"))) return sponsor ? "/sponsor/queries" : "/site/queries";
    if (!sponsor) return `/site/s/${row.protocol_id}/patients`;
    if (["visit_submitted", "visit_approved"].includes(row.kind) && can("listing.view")) return `/sponsor/p/${row.protocol_id}/data`;
    return `/sponsor/p/${row.protocol_id}/review`;
  };
  return <div className="workspace-dashboard">
    <NavigationActions><button className="workspace-refresh" type="button" aria-label="Refresh notifications" onClick={refresh} disabled={loading || busy}><Icon name="refresh" className="workspace-icon" /></button></NavigationActions>
    <div className="workspace-body">
      <div className="workspace-heading"><div><p className="study-eyebrow">Workspace alerts</p><h1>Notifications</h1><p>Queries, visit submissions and review updates, in one place.</p></div><span className="notification-unread-total">{current && !current.error ? unread : "—"} unread in this view</span></div>
      <div className="notification-controls">
        <div className="row row-wrap"><label className="check"><input type="checkbox" checked={unreadOnly} disabled={loading || busy} onChange={(event) => updateFilter("unread", event.target.checked ? "1" : "")} />Unread only</label>
          <label className="workspace-visually-hidden" htmlFor="notification-protocol">Protocol</label><select className="input" id="notification-protocol" value={protocol} onChange={(event) => updateFilter("protocol", event.target.value)} disabled={busy}><option value="">All protocols</option>{protocol && !seen.has(Number(protocol)) && <option value={protocol}>Selected protocol</option>}{[...seen].map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select>
          <label className="workspace-visually-hidden" htmlFor="notification-kind">Kind</label><select className="input" id="notification-kind" value={kind} onChange={(event) => updateFilter("kind", event.target.value)} disabled={busy}><option value="">All kinds</option>{Object.entries(KIND_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        </div>
        <button className="btn btn-secondary btn-sm" type="button" onClick={() => void act(() => api.readAllNotifications(protocol ? Number(protocol) : undefined))} disabled={loading || busy || !unread} title={protocol ? "Mark every notification for this protocol as read" : "Mark every notification in your inbox as read"}>Mark all as read</button>
      </div>
      {error && <div className="workspace-error" role="alert"><strong>Couldn’t update notifications.</strong><p>{error}</p><button className="btn btn-secondary btn-sm mt-3" type="button" onClick={refresh} disabled={loading || busy}>Try again</button></div>}
      {loading && <p className="workspace-empty" role="status">Loading notifications…</p>}
      {current && !error && !filtered.length && <div className="workspace-study-panel workspace-empty"><h2>{unreadOnly ? "You’re caught up" : "No notifications yet"}</h2><p>{protocol || kind ? "No notifications match these filters." : "New queries, patient-visit submissions and review updates will appear here."}</p></div>}
      <div className="notification-list">{visible.map((row) => <article className={`notification-item${row.read_at ? "" : " unread"}`} key={row.id}>
        <span className="notification-symbol"><Icon name={row.kind.includes("query") ? "queries" : "progress"} /></span>
        <div className="notification-content"><div className="notification-item-heading"><h2>{KIND_LABEL[row.kind] ?? row.kind}</h2>{!row.read_at && <span className="notification-new">Unread</span>}</div><p><strong>{row.protocol_name ?? "Protocol"}</strong>{row.subject && <> · {row.subject}</>}{row.visit && <> · {row.visit}</>}</p><p>{row.body}</p><time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString()}</time>
          <div className="notification-item-actions"><button className="btn btn-secondary btn-sm" type="button" disabled={busy || loading} onClick={() => void act(() => row.read_at ? Promise.resolve() : api.readNotification(row.id), destination(row))}>Open related work</button>{!row.read_at && <button className="notification-read" type="button" disabled={busy || loading} onClick={() => void act(() => api.readNotification(row.id))}>Mark as read</button>}</div>
        </div>
      </article>)}</div>
      {filtered.length > limit && <button className="btn btn-secondary btn-sm mt-4" type="button" disabled={busy} onClick={() => setLimit((previous) => previous + 25)}>Show more notifications</button>}
      <p className="notification-footnote">Read status is personal to your account. These are in-app alerts; no email or browser push is sent. Visit submission means hospital staff sent a patient’s visit for review, not final approval.</p>
    </div>
  </div>;
}
