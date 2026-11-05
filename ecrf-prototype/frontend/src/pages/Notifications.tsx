import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { NotificationItem } from "../api/types";
import Icon from "../components/Icon";
import "../styles/workspace.css";
import "../styles/notifications.css";

export default function Notifications() {
  const navigate = useNavigate();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [unreadCount, setUnreadCount] = useState<number | null>(null);
  const [next, setNext] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async (beforeId?: number) => {
    setLoading(true);
    try {
      const page = await api.notifications({ unread_only: unreadOnly, ...(beforeId ? { before_id: beforeId } : {}) });
      setItems((previous) => beforeId ? [...previous, ...page.items] : page.items);
      setUnreadCount(page.unread_count); setNext(page.next_before_id); setError(null);
    } catch (failure) { setError((failure as Error).message); }
    finally { setLoading(false); }
  }, [unreadOnly]);
  useEffect(() => { void refresh(); }, [refresh]);
  const updated = () => window.dispatchEvent(new Event("notifications-updated"));
  const open = async (item: NotificationItem) => {
    setBusy(true); setError(null);
    try {
      if (!item.read_at) await api.readNotification(item.id);
      updated(); navigate(item.destination);
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  };
  const markRead = async (item?: NotificationItem) => {
    if (!item && !items.length) return;
    setBusy(true); setError(null);
    try {
      if (item) await api.readNotification(item.id);
      else await api.readAllNotifications(items[0].id);
      updated(); await refresh();
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  };

  return <div className="workspace-dashboard">
    <header className="workspace-topbar"><nav className="workspace-breadcrumb" aria-label="Breadcrumb"><Link to="/sponsor">Workspace</Link><Icon name="chevron" className="workspace-icon" /><strong>Notifications</strong></nav><button className="workspace-refresh" type="button" aria-label="Refresh notifications" onClick={() => refresh()} disabled={loading || busy}><Icon name="refresh" className="workspace-icon" /></button></header>
    <div className="workspace-body">
      <div className="workspace-heading"><div><p className="study-eyebrow">Hospital alerts</p><h1>Notifications</h1><p>New hospital queries and entire-eCRF submissions, in one place.</p></div><span className="notification-unread-total">{unreadCount ?? "—"} unread</span></div>
      <div className="notification-controls"><label className="check"><input type="checkbox" checked={unreadOnly} disabled={loading || busy} onChange={(event) => setUnreadOnly(event.target.checked)} />Unread only</label><button className="btn btn-secondary btn-sm" type="button" onClick={() => markRead()} disabled={loading || busy || !unreadCount || !items.length}>Mark all as read</button></div>
      {error && <div className="workspace-error" role="alert"><strong>Couldn’t update notifications.</strong><p>{error}</p><button className="btn btn-secondary btn-sm mt-3" type="button" onClick={() => refresh()} disabled={loading || busy}>Try again</button></div>}
      {loading && !items.length && <p className="workspace-empty" role="status">Loading notifications…</p>}
      {!loading && !error && !items.length && <div className="workspace-study-panel workspace-empty"><h2>{unreadOnly ? "You’re caught up" : "No notifications yet"}</h2><p>New hospital queries and explicitly submitted eCRFs will appear here.</p></div>}
      <div className="notification-list">{items.map((item) => <article className={`notification-item${item.read_at ? "" : " unread"}`} key={item.id}><span className="notification-symbol"><Icon name={item.kind === "hospital_query" ? "queries" : "progress"} /></span><div className="notification-content"><div className="notification-item-heading"><h2>{item.title}</h2>{!item.read_at && <span className="notification-new">Unread</span>}</div><p><strong>{item.hospital_name}</strong> · {item.protocol_name}</p><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time><div className="notification-item-actions"><button className="btn btn-secondary btn-sm" type="button" disabled={busy || loading} onClick={() => open(item)}>{item.kind === "hospital_query" ? "Open query" : "View hospital eCRF"}</button>{!item.read_at && <button className="notification-read" type="button" disabled={busy || loading} onClick={() => markRead(item)}>Mark as read</button>}</div></div></article>)}</div>
      {next && <button className="btn btn-secondary btn-sm mt-4" type="button" disabled={loading || busy} onClick={() => refresh(next)}>{loading ? "Loading…" : "Load older notifications"}</button>}
      <p className="notification-footnote">Read status is personal to your account. In-app alerts refresh about every 30 seconds while the app is visible; no email or browser push is sent. Submission means the hospital declared its work ready for review—not sponsor approval.</p>
    </div>
  </div>;
}
