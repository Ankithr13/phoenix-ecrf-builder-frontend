import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api/client";
import Icon from "./Icon";
import "../styles/notifications.css";

export default function NotificationBell() {
  const { pathname } = useLocation();
  const [unread, setUnread] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const newest = useRef<number | null>(null);

  useEffect(() => {
    let active = true;
    let pending = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const page = await api.notifications({ limit: 1 });
        if (!active) return;
        const latestId = page.items[0]?.id ?? 0;
        setAnnouncement(newest.current !== null && latestId > newest.current
          ? `New hospital notification received. ${page.unread_count} unread.` : "");
        newest.current = latestId;
        setUnread(page.unread_count);
        setFailed(false);
      } catch {
        if (active) setFailed(true);
      } finally { pending = false; }
    };
    const whenVisible = () => { if (document.visibilityState === "visible") void refresh(); };
    void refresh();
    const interval = window.setInterval(whenVisible, 30000);
    window.addEventListener("focus", whenVisible);
    window.addEventListener("notifications-updated", whenVisible);
    document.addEventListener("visibilitychange", whenVisible);
    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener("focus", whenVisible);
      window.removeEventListener("notifications-updated", whenVisible);
      document.removeEventListener("visibilitychange", whenVisible);
    };
  }, [pathname]);

  return <>
    <Link className={`notification-bell${failed ? " notification-bell-offline" : ""}`} to="/sponsor/notifications" aria-label={failed ? "Notifications, updates unavailable" : unread === null ? "Notifications" : `Notifications, ${unread} unread`} title={failed ? "Couldn’t refresh notifications. Open to retry." : "Hospital notifications"}>
      <Icon name="bell" />
      {unread !== null && unread > 0 && <span className="notification-bell-count" aria-hidden="true">{unread > 99 ? "99+" : unread}</span>}
      {failed && <span className="notification-bell-warning" aria-hidden="true">!</span>}
    </Link>
    <span className="workspace-visually-hidden" role="status" aria-live="polite">{announcement}</span>
  </>;
}
