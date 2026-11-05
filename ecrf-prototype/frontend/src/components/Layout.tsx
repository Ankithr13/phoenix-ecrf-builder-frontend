import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/useAuth";

const ID_IN_PATH = /^\/(sponsor\/p|site\/s)\/(\d+)/;

const ROLE_LABEL: Record<string, string> = {
  sponsor: "Sponsor", site_staff: "Site staff",
};

const ICON_PATHS = {
  dashboard: "M3 3h7v7H3ZM14 3h7v4h-7ZM14 11h7v10h-7ZM3 14h7v7H3Z",
  upload: "M12 16V3M7 8l5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5",
  chevron: "M9 5l7 7-7 7",
  protocols: "M9 5H6a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3M9 3h6v4H9zM8 12h8M8 17h5",
  queries: "M21 11a8 8 0 0 1-8 8H7l-5 3V11a8 8 0 0 1 8-8h3a8 8 0 0 1 8 8ZM7 9h9M7 13h6",
  visits: "M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2ZM8 14h2M14 14h2M8 18h2",
  forms: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6M8 12h8M8 16h8",
  sites: "M3 21h18M5 21V7l7-4 7 4v14M9 21v-5h6v5M9 8h1M14 8h1M9 12h1M14 12h1",
  data: "M14 2H6a2 2 0 0 0-2 2v5M4 19v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6M2 14h10M8 10l4 4-4 4",
  reports: "M3 3v18h18M8 16v-5M13 16V6M18 16v-8",
  patients: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  signOut: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "M6 6l12 12M6 18 18 6",
};

type SidebarIconName = keyof typeof ICON_PATHS;
type NavigationItem = { label: string; icon: SidebarIconName; to: string | null; end?: boolean; badge?: ReactNode; active?: boolean; unavailableReason?: string };

function SidebarIcon({ name }: { name: SidebarIconName }) {
  return (
    <svg className="sidebar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

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
  const inStudies = pathname === "/sponsor" || pathname === "/sponsor/protocols" || pathname.startsWith("/sponsor/studies/") || /^\/sponsor\/p\/\d+\/(visits|sites)$/.test(pathname);
  const dashboardItems: NavigationItem[] = [{
    label: "Dashboard", icon: "dashboard", to: null,
    unavailableReason: "The workspace dashboard is coming in a separate feature.",
    badge: <span className="nav-soon">Soon</span>,
  }];
  const workspaceItems: NavigationItem[] = sponsor ? [
    ...(can("protocol.upload") ? [{ label: "Upload Protocol", icon: "upload", to: "/sponsor/upload" } as NavigationItem] : []),
    { label: "eCRF Management", icon: "forms", to: id ? `/sponsor/p/${id}/review` : "/sponsor/ecrfs", active: pathname === "/sponsor/ecrfs" || /^\/sponsor\/p\/\d+\/review$/.test(pathname) },
    { label: "Clinical Data Review", icon: "data", to: id ? `/sponsor/p/${id}/data` : "/sponsor/data", active: pathname === "/sponsor/data" || /^\/sponsor\/p\/\d+\/data$/.test(pathname) },
    { label: "Analytics & Reports", icon: "reports", to: id ? `/sponsor/p/${id}/dashboard` : "/sponsor/reports", active: pathname === "/sponsor/reports" || /^\/sponsor\/p\/\d+\/dashboard$/.test(pathname) },
    { label: "Queries", icon: "queries", to: "/sponsor/queries", badge },
  ] : [
    { label: "Studies", icon: "protocols", to: "/site", end: true },
    { label: "Queries", icon: "queries", to: "/site/queries", badge },
  ];
  const studyItems: NavigationItem[] = sponsor ? [
    { label: "All studies", icon: "protocols", to: "/sponsor", end: true },
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
