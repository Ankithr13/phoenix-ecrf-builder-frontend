import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api/client";
import type { Health } from "../api/types";
import { useAuth } from "../auth/useAuth";
import { ROLE_LABEL } from "../format";

const ID_IN_PATH = /^\/(sponsor\/p|site\/s)\/(\d+)/;

export default function Layout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const { me, signOut, can } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [openItems, setOpenItems] = useState<number>(0);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealthError(true));
  }, []);

  // The badge is the alert: queries where it is this user's turn, either
  // to answer the other side or to close one they raised that has been
  // answered. The server works that out per row. Refreshed on navigation.
  const hasQueries = can("query.raise") || can("query.answer") || can("query.close");
  useEffect(() => {
    if (!me || !hasQueries) return;
    api.queries().then((q) => setOpenItems(q.filter((x) => x.for_me).length)).catch(() => setOpenItems(0));
  }, [me, pathname, hasQueries]);

  const [unread, setUnread] = useState(0);
  useEffect(() => {
    if (!me || me.must_change_password) return;
    const refresh = () => { api.unreadNotifications().then((r) => setUnread(r.unread)).catch(() => setUnread(0)); };
    refresh();
    window.addEventListener("notifications-changed", refresh);
    return () => window.removeEventListener("notifications-changed", refresh);
  }, [me, pathname]);

  const badge = openItems > 0 ? <span className="nav-badge">{openItems}</span> : null;
  const m = pathname.match(ID_IN_PATH);
  const id = m ? m[2] : null;
  const sponsor = me?.org.type === "sponsor";
  const pillState = health ? "" : healthError ? " offline" : " pending";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo">
            <img src="/logo.png" alt="Phoenix Clinical Research" />
          </div>
          <div className="brand-name">eCRF Builder</div>
        </div>

        {me && (
          <div className="identity">
            <div className="identity-org">{me.org.name}</div>
            <div className="identity-user">
              {me.user.name} <span className="muted-2">· {ROLE_LABEL[me.role]}</span>
            </div>
            <div className="row">
              <button type="button" className="btn-link identity-out" onClick={signOut}>Sign out</button>
              <NavLink to="/change-password" className="btn-link identity-out">Change password</NavLink>
            </div>
          </div>
        )}

        <nav className="nav" aria-label="Main">
          {sponsor ? (
            <>
              {can("users.manage") && <NavLink to="/admin">Admin</NavLink>}
              <NavLink to="/sponsor" end>Protocols</NavLink>
              {hasQueries && <NavLink to="/sponsor/queries">Queries{badge}</NavLink>}
              <NavLink to="/notifications">Notifications{unread > 0 && <span className="nav-badge">{unread}</span>}</NavLink>
              {id && (
                <div className="nav-group">
                  <div className="nav-group-label">protocol {id}</div>
                  {can("protocol.extract") && <NavLink to={`/sponsor/p/${id}/visits`}>Visits</NavLink>}
                  <NavLink to={`/sponsor/p/${id}/review`}>Review</NavLink>
                  {(can("form.edit") || can("protocol.lock")) && <NavLink to={`/sponsor/p/${id}/checks`}>Edit checks</NavLink>}
                  {can("sites.assign") && <NavLink to={`/sponsor/p/${id}/sites`}>Sites</NavLink>}
                  {can("listing.view") && <NavLink to={`/sponsor/p/${id}/data`}>Data review</NavLink>}
                  {can("dashboard.view") && <NavLink to={`/sponsor/p/${id}/dashboard`}>Dashboard</NavLink>}
                  <NavLink to={`/sponsor/p/${id}/notifications`}>Study notifications</NavLink>
                </div>
              )}
            </>
          ) : (
            <>
              <NavLink to="/site" end>Studies</NavLink>
              {hasQueries && <NavLink to="/site/queries">Queries{badge}</NavLink>}
              <NavLink to="/notifications">Notifications{unread > 0 && <span className="nav-badge">{unread}</span>}</NavLink>
              {id && (
                <div className="nav-group">
                  <div className="nav-group-label">study {id}</div>
                  <NavLink to={`/site/s/${id}/patients`}>Patients</NavLink>
                  <NavLink to={`/site/s/${id}/notifications`}>Study notifications</NavLink>
                </div>
              )}
            </>
          )}
        </nav>

        <div className="sidebar-foot">
          <NavLink to="/glossary" className="btn-link small glossary-link">Glossary: what the words mean</NavLink>
          <span className={`backend-pill${pillState}`} title="Extraction backend">
            {health ? `${health.backend} · ${health.model}` : healthError ? "backend offline" : "connecting…"}
          </span>
        </div>
      </aside>
      <main>{children}</main>
    </div>
  );
}
