import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api/client";
import type { Health } from "../api/types";
import { useAuth } from "../auth/useAuth";

const ID_IN_PATH = /^\/(sponsor\/p|site\/s)\/(\d+)/;

const ROLE_LABEL: Record<string, string> = {
  builder: "Builder", approver: "Approver", site_staff: "Site staff",
};

export default function Layout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const { me, signOut } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [openItems, setOpenItems] = useState<number>(0);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealthError(true));
  }, []);

  // The badge is the alert: sites count queries waiting for an answer,
  // sponsors count answers waiting to be closed. Refreshed on navigation.
  useEffect(() => {
    if (!me) return;
    const want = me.org.type === "site" ? "open" : "answered";
    api.queries(want).then((q) => setOpenItems(q.length)).catch(() => setOpenItems(0));
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
              {me.user.name} <span className="muted-2">· {ROLE_LABEL[me.role] ?? me.role}</span>
            </div>
            <button type="button" className="btn-link identity-out" onClick={signOut}>Sign out</button>
          </div>
        )}

        <nav className="nav" aria-label="Main">
          {sponsor ? (
            <>
              <NavLink to="/sponsor" end>Protocols</NavLink>
              <NavLink to="/sponsor/queries">Queries{badge}</NavLink>
              {id && (
                <div className="nav-group">
                  <div className="nav-group-label">protocol {id}</div>
                  <NavLink to={`/sponsor/p/${id}/visits`}>Visits</NavLink>
                  <NavLink to={`/sponsor/p/${id}/review`}>Review</NavLink>
                  <NavLink to={`/sponsor/p/${id}/sites`}>Sites</NavLink>
                  <NavLink to={`/sponsor/p/${id}/data`}>Data review</NavLink>
                  <NavLink to={`/sponsor/p/${id}/dashboard`}>Dashboard</NavLink>
                </div>
              )}
            </>
          ) : (
            <>
              <NavLink to="/site" end>Studies</NavLink>
              <NavLink to="/site/queries">Queries{badge}</NavLink>
              {id && (
                <div className="nav-group">
                  <div className="nav-group-label">study {id}</div>
                  <NavLink to={`/site/s/${id}/patients`}>Patients</NavLink>
                </div>
              )}
            </>
          )}
        </nav>

        <div className="sidebar-foot">
          <span className={`backend-pill${pillState}`} title="Extraction backend">
            {health ? `${health.backend} · ${health.model}` : healthError ? "backend offline" : "connecting…"}
          </span>
        </div>
      </aside>
      <main>{children}</main>
    </div>
  );
}
