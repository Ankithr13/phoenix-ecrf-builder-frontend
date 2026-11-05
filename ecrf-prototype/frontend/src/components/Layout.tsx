import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/useAuth";
import SidebarIcon, { type IconName } from "./Icon";
import NotificationBell from "./NotificationBell";
import NavigationBreadcrumbs from "./NavigationBreadcrumbs";
import { NavigationContext } from "../navigation/context";
import { useNavigationState } from "../navigation/useNavigationState";
import "../styles/navigation.css";

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
  const [actionsContainer, setActionsContainer] = useState<HTMLDivElement | null>(null);
  const navigation = useNavigationState();
  const navRef = useRef<HTMLElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const id = navigation.protocolId;
  useEffect(() => { navRef.current?.scrollTo({ top: 0 }); }, [id, navigation.studyId]);
  useEffect(() => { setMenuOpen(false); }, [pathname]);

  // The badge is the alert: queries where it is this user's turn, either
  // to answer the other side or to close one they raised that has been
  // answered. The server works that out per row. Refreshed on navigation.
  useEffect(() => {
    if (!me) return;
    api.queries().then((q) => setOpenItems(q.filter((x) => x.for_me).length)).catch(() => setOpenItems(0));
  }, [me, pathname]);

  const badge = openItems > 0 ? <span className="nav-badge" aria-label={`${openItems} queries need your attention`}>{openItems}</span> : null;
  const sponsor = me?.org.type === "sponsor";
  const closeMenu = () => setMenuOpen(false);
  const initials = me?.user.name.trim().split(/\s+/).map((part) => part[0]).slice(0, 2).join("");
  const inStudies = pathname === "/sponsor/studies" || pathname === "/sponsor/protocols" || pathname.startsWith("/sponsor/studies/");
  const dashboardItems: NavigationItem[] = [{
    label: "Dashboard", icon: "dashboard", to: "/sponsor", end: true,
  }];
  const workspaceItems: NavigationItem[] = sponsor ? [
    ...(can("protocol.upload") ? [{ label: "Upload Protocol", icon: "upload", to: "/sponsor/upload" } as NavigationItem] : []),
    { label: "eCRF Management", icon: "forms", to: "/sponsor/ecrfs" },
    { label: "eCRF Status", icon: "progress", to: "/sponsor/ecrf-status" },
    { label: "Clinical Data Review", icon: "data", to: "/sponsor/data" },
    { label: "Analytics & Reports", icon: "reports", to: "/sponsor/reports" },
    { label: "Queries", icon: "queries", to: "/sponsor/queries", badge },
  ] : [
    { label: "Studies", icon: "protocols", to: "/site", end: true },
    { label: "Queries", icon: "queries", to: "/site/queries", badge },
  ];
  const studyItems: NavigationItem[] = sponsor ? [
    { label: "All studies", icon: "protocols", to: "/sponsor/studies", end: true },
    { label: "All protocols", icon: "forms", to: "/sponsor/protocols" },
  ] : [];
  const protocolItems: NavigationItem[] = id && navigation.data ? sponsor ? [
    { label: "Visits & extraction", icon: "visits", to: `/sponsor/p/${id}/visits` },
    { label: "eCRF Review", icon: "forms", to: `/sponsor/p/${id}/review` },
    { label: "Sites", icon: "sites", to: `/sponsor/p/${id}/sites` },
    { label: "Data review", icon: "data", to: `/sponsor/p/${id}/data` },
    { label: "Reports", icon: "reports", to: `/sponsor/p/${id}/dashboard` },
  ] : [{ label: "Patients", icon: "patients", to: `/site/s/${id}/patients` }] : [];

  return (
    <NavigationContext.Provider value={{ ...navigation, actionsContainer }}>
    <div className="shell">
      <aside className={`sidebar${menuOpen ? " sidebar-open" : ""}`} onKeyDown={(event) => { if (event.key === "Escape" && menuOpen) { closeMenu(); toggleRef.current?.focus(); } }}>
        <div className="sidebar-heading">
          <NavLink className="brand" to={sponsor ? "/sponsor" : "/site"} onClick={closeMenu} aria-label="Phoenix Clinical home">
            <img className="brand-logo" src="/logo.png" alt="Phoenix Clinical Research" />
          </NavLink>
          {sponsor && me && <NotificationBell key={me.user.id} />}
          <button ref={toggleRef} type="button" className="sidebar-toggle" aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-expanded={menuOpen} aria-controls="workspace-navigation" onClick={() => setMenuOpen(!menuOpen)}>
            <SidebarIcon name={menuOpen ? "close" : "menu"} />
          </button>
        </div>

        <div className="sidebar-content" id="workspace-navigation">
          <nav className="nav" aria-label="Main" ref={navRef}>
            {(id || navigation.studyId) && <div>
              <section className="navigation-context" aria-label="Current workspace context" aria-busy={navigation.loading}>
                <p className="navigation-context-label">{id ? sponsor ? "Selected protocol" : "Assigned eCRF" : "Selected study"}</p>
                {navigation.loading && <p className="navigation-context-help" role="status">Loading details…</p>}
                {navigation.error && <><p className="navigation-context-help" role="status">Details unavailable. You can still use the workspace links below.</p><button className="navigation-context-retry" type="button" onClick={navigation.retry}>Retry details</button></>}
                {navigation.study && <><span className="navigation-context-study">{navigation.study.code}</span><strong className="navigation-context-name">{navigation.study.name}</strong></>}
                {navigation.data && <>
                  {!navigation.study && <span className="navigation-context-study">{sponsor ? "Unassigned protocol" : "Assigned protocol"}</span>}
                  <strong className="navigation-context-name">{navigation.data.protocol.name}</strong>
                  <span className="navigation-context-state">{navigation.data.protocol.state === "locked" ? "Locked eCRF" : navigation.data.protocol.state === "draft" ? "Draft eCRF" : "Not extracted yet"}</span>
                  {navigation.data.subject && <p className="navigation-context-help">Patient <strong className="mono">{navigation.data.subject.code}</strong></p>}
                </>}
                {navigation.studyId && navigation.study && <p className="navigation-context-help">Open a protocol in this study to see its tools.</p>}
                <div className="navigation-context-links">
                  {sponsor && id && <Link to={navigation.study ? `/sponsor/studies/${navigation.study.id}` : "/sponsor/protocols"} onClick={closeMenu}>{navigation.study ? "← Back to study" : "← All protocols"}</Link>}
                  <Link to={sponsor ? "/sponsor/studies" : "/site"} onClick={closeMenu}>{sponsor ? "All studies" : "← Change study"}</Link>
                </div>
              </section>
              {protocolItems.length > 0 && <div className="nav-protocol-tools"><div className="nav-group-label navigation-protocol-heading">{sponsor ? "Protocol tools" : "Hospital tools"}</div><SidebarLinks items={protocolItems} onNavigate={closeMenu} /></div>}
            </div>}
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
      <main><header className="navigation-header"><NavigationBreadcrumbs /><div className="navigation-actions" ref={setActionsContainer} /></header>{children}</main>
    </div>
    </NavigationContext.Provider>
  );
}
