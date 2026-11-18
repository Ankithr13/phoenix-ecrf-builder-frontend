import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api/client";
import Icon from "./Icon";

export default function NotificationBell() {
  const { pathname } = useLocation();
  const [unread, setUnread] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    let request = 0;
    const refresh = () => {
      if (document.visibilityState === "hidden") return;
      const current = ++request;
      api.unreadNotifications().then((response) => { if (active && current === request) { setUnread(response.unread); setFailed(false); } })
        .catch(() => { if (active && current === request) setFailed(true); });
    };
    refresh();
    const timer = window.setInterval(refresh, 30000);
    window.addEventListener("focus", refresh);
    window.addEventListener("notifications-changed", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => { active = false; window.clearInterval(timer); window.removeEventListener("focus", refresh); window.removeEventListener("notifications-changed", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [pathname]);
  return <Link className="notification-bell" to="/notifications" aria-label={failed ? "Notifications — count unavailable" : unread === null ? "Notifications — loading count" : `Notifications, ${unread} unread`} title={failed ? "Could not refresh notifications. Open the inbox to retry." : "Notifications"}>
    <Icon name="bell" />{failed ? <span className="notification-bell-warning">!</span> : unread !== null && unread > 0 ? <span className="notification-bell-count">{unread > 99 ? "99+" : unread}</span> : null}
  </Link>;
}
