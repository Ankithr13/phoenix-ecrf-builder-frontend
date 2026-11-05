import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/useAuth";
import SidebarIcon, { type IconName } from "./Icon";

const ID_IN_PATH = /^\/(sponsor\/p|site\/s)\/(\d+)/;

const ROLE_LABEL: Record<string, string> = {
  sponsor: "Sponsor", site_staff: "Site staff",
};

type NavigationItem = { label: string; icon: IconName; to: string | null; end?: boolean; badge?: ReactNode; active?: boolean; unavailableReason?: string };

function SidebarLinks({ items, onNavigate }: { items: NavigationItem[]; onNavigate: () => void }) {
  return items.map((item) => item.to ? (
    <NavLink key={item.label} to={item.to} end={item.end} onClick={onNavigate} className={({ isActive }) => (item.active ?? isActive) ? "active" : undefined}>
      <SidebarIcon name={item.icon} />
      <span className="nav-label">{item.label}</span>
      {item.badge}
    </NavLink>
  ) : (
    <span key={item.label} className="nav-unavailable" role="link" aria-disabled="true" title={item.unavailableReason ?? "Open a protocol to access this section"}>
      <SidebarIcon name={item.icon} />
      <span className="nav-label">{item.label}</span>
      {item.badge}
    </span>
  ));
}

export default function Layout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const { me, signOut, can } = useAuth();
  const [openItems, setOpenItems] = useState<number>(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [studiesOpen, setStudiesOpen] = useState(true);

  // The badge is the alert: queries where it is this user's turn, either
  // to answer the other side or to close one they raised that has been
  // answered. The server works that out per row. Refreshed on navigation.
  useEffect(() => {
    if (!me) return;
    api.queries().then((q) => setOpenItems(q.filter((x) => x.for_me).length)).catch(() => setOpenItems(0));
  }, [me, pathname]);

  const badge = openItems > 0 ? <span className="nav-badge" aria-label={`${openItems} queries need your attention`}>{openItems}</span> : null;
  const m = pathname.match(ID_IN_PATH);
  const id = m ? m[2] : null;
  const sponsor = me?.org.type === "sponsor";
  const closeMenu = () => setMenuOpen(false);
  const initials = me?.user.name.trim().split(/\s+/).map((part) => part[0]).slice(0, 2).join("");
  const inStudies = pathname === "/sponsor/studies" || pathname === "/sponsor/protocols" || pathname.startsWith("/sponsor/studies/") || /^\/sponsor\/p\/\d+\/(visits|sites)$/.test(pathname);
  const dashboardItems: NavigationItem[] = [{
    label: "Dashboard", icon: "dashboard", to: "/sponsor", end: true,
  }];
  const workspaceItems: NavigationItem[] = sponsor ? [
    ...(can("protocol.upload") ? [{ label: "Upload Protocol", icon: "upload", to: "/sponsor/upload" } as NavigationItem] : []),
    { label: "eCRF Management", icon: "forms", to: id ? `/sponsor/p/${id}/review` : "/sponsor/ecrfs", active: pathname === "/sponsor/ecrfs" || /^\/sponsor\/p\/\d+\/review$/.test(pathname) },
    { label: "eCRF Status", icon: "progress", to: "/sponsor/ecrf-status" },
    { label: "Clinical Data Review", icon: "data", to: id ? `/sponsor/p/${id}/data` : "/sponsor/data", active: pathname === "/sponsor/data" || /^\/sponsor\/p\/\d+\/data$/.test(pathname) },
    { label: "Analytics & Reports", icon: "reports", to: id ? `/sponsor/p/${id}/dashboard` : "/sponsor/reports", active: pathname === "/sponsor/reports" || /^\/sponsor\/p\/\d+\/dashboard$/.test(pathname) },
    { label: "Queries", icon: "queries", to: "/sponsor/queries", badge },
  ] : [
    { label: "Studies", icon: "protocols", to: "/site", end: true },
    { label: "Queries", icon: "queries", to: "/site/queries", badge },
  ];
  const studyItems: NavigationItem[] = sponsor ? [
    { label: "All studies", icon: "protocols", to: "/sponsor/studies", end: true },
    { label: "All protocols", icon: "forms", to: "/sponsor/protocols" },
    ...(id ? [
      { label: "Visits", icon: "visits", to: `/sponsor/p/${id}/visits` } as NavigationItem,
      { label: "Sites", icon: "sites", to: `/sponsor/p/${id}/sites` } as NavigationItem,
    ] : []),
  ] : id ? [
    { label: "Patients", icon: "patients", to: `/site/s/${id}/patients` },
  ] : [];

  return (
    <div className="shell">
      <aside className={`sidebar${menuOpen ? " sidebar-open" : ""}`} onKeyDown={(event) => { if (event.key === "Escape") closeMenu(); }}>
        <div className="sidebar-heading">
          <NavLink className="brand" to={sponsor ? "/sponsor" : "/site"} onClick={closeMenu} aria-label="Phoenix Clinical home">
            <img className="brand-logo" src="/logo.png" alt="Phoenix Clinical Research" />
          </NavLink>
          <button type="button" className="sidebar-toggle" aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-expanded={menuOpen} aria-controls="workspace-navigation" onClick={() => setMenuOpen(!menuOpen)}>
            <SidebarIcon name={menuOpen ? "close" : "menu"} />
          </button>
        </div>

        <div className="sidebar-content" id="workspace-navigation">
          <nav className="nav" aria-label="Main">
            <div className="nav-section">
              <div className="nav-group-label">Workspace</div>
              {sponsor && (
                <>
                  <SidebarLinks items={dashboardItems} onNavigate={closeMenu} />
                  <button type="button" className={`nav-folder${inStudies ? " active" : ""}`} aria-expanded={studiesOpen} aria-controls="studies-navigation" onClick={() => setStudiesOpen(!studiesOpen)}>
                    <SidebarIcon name="protocols" />
                    <span className="nav-label">Studies</span>
                    <span className={`nav-chevron${studiesOpen ? " expanded" : ""}`}><SidebarIcon name="chevron" /></span>
                  </button>
                  <div className="nav-submenu" id="studies-navigation" hidden={!studiesOpen}>
                    <SidebarLinks items={studyItems} onNavigate={closeMenu} />
                  </div>
                </>
              )}
              <SidebarLinks items={workspaceItems} onNavigate={closeMenu} />
            </div>
            {!sponsor && studyItems.length > 0 && (
              <div className="nav-section">
                <div className="nav-group-label">{id ? `${sponsor ? "Protocol" : "Study"} ${id}` : "Protocol workspace"}</div>
                <SidebarLinks items={studyItems} onNavigate={closeMenu} />
              </div>
            )}
          </nav>

          <div className="sidebar-foot">
            {me && (
              <div className="identity">
                <span className="identity-avatar" aria-hidden="true">{initials}</span>
                <div className="identity-details">
                  <div className="identity-user">{me.user.name}</div>
                  <div className="identity-org" title={me.org.name}>{ROLE_LABEL[me.role] ?? me.role} · {me.org.name}</div>
                </div>
                <button type="button" className="identity-out" onClick={signOut} aria-label="Sign out" title="Sign out">
                  <SidebarIcon name="signOut" />
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>
      <main>{children}</main>
    </div>
  );
}
