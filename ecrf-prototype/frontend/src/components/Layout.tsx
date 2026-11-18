import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { api } from "../api/client";
import { ROLE_LABEL } from "../format";
import { useAuth } from "../auth/useAuth";
import SidebarIcon, { type IconName } from "./Icon";
import NotificationBell from "./NotificationBell";
import NavigationBreadcrumbs from "./NavigationBreadcrumbs";
import { NavigationContext } from "../navigation/context";
import { useNavigationState } from "../navigation/useNavigationState";
import "../styles/navigation.css";



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
  const accountRef = useRef<HTMLDetailsElement>(null);
  const leaveGuard = useRef<((action: () => void) => void) | null>(null);
  const registerLeaveGuard = useCallback((guard: ((action: () => void) => void) | null) => { leaveGuard.current = guard; }, []);
  const id = navigation.protocolId;
  useEffect(() => { navRef.current?.scrollTo({ top: 0 }); }, [id]);
  useEffect(() => { setMenuOpen(false); if (accountRef.current) accountRef.current.open = false; }, [pathname]);

  // The badge is the alert: queries where it is this user's turn, either
  // to answer the other side or to close one they raised that has been
  // answered. The server works that out per row. Refreshed on navigation.
  useEffect(() => {
    if (!me || me.must_change_password || !(can("query.raise") || can("query.answer") || can("query.close"))) return;
    api.queries().then((q) => setOpenItems(q.filter((x) => x.for_me).length)).catch(() => setOpenItems(0));
  }, [me, pathname, can]);

  const badge = openItems > 0 ? <span className="nav-badge" aria-label={`${openItems} queries need your attention`}>{openItems}</span> : null;
  const sponsor = me?.org.type === "sponsor";
  const closeMenu = () => setMenuOpen(false);
  const initials = me?.user.name.trim().split(/\s+/).map((part) => part[0]).slice(0, 2).join("");
  const inStudies = pathname === "/sponsor/studies" || pathname === "/sponsor/protocols" || pathname.startsWith("/sponsor/studies/");
  const dashboardItems: NavigationItem[] = [{
    label: "Dashboard", icon: "dashboard", to: "/sponsor", end: true,
  }];
  const workspaceItems: NavigationItem[] = sponsor ? [
    ...(can("users.manage") ? [{ label: "Admin", icon: "patients", to: "/admin" } as NavigationItem] : []),
    { label: "Upload Protocol", icon: "upload", to: "/sponsor/upload" },
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

  if (!sponsor && can("notifications.view")) workspaceItems.push({ label: "Notifications", icon: "bell", to: "/notifications" });
  if (id && navigation.data && can("listing.view")) protocolItems.push({ label: "Data listing", icon: "forms", to: `/listing/${id}` });
  if (id && navigation.data && !sponsor && can("dashboard.view")) protocolItems.push({ label: "Dashboard", icon: "dashboard", to: `/site/s/${id}/dashboard` });
  const visible = (items: NavigationItem[]) => items.filter((item) => {
    const required: Record<string, string> = { Dashboard: "dashboard.view", "eCRF Status": "dashboard.subject_level", "Clinical Data Review": "listing.view", "Data review": "listing.view", "Data listing": "listing.view", "Analytics & Reports": "dashboard.view", Reports: "dashboard.view", Sites: "sites.assign", "Visits & extraction": "protocol.extract" };
    if (item.label === "Queries") return can("query.raise") || can("query.answer") || can("query.close");
    return !required[item.label] || can(required[item.label]);
  });

  return (
    <NavigationContext.Provider value={{ ...navigation, actionsContainer, registerLeaveGuard }}>
    <div className="shell">
      <aside className={`sidebar${menuOpen ? " sidebar-open" : ""}`} onKeyDown={(event) => { if (event.key === "Escape" && menuOpen) { closeMenu(); toggleRef.current?.focus(); } }}>
        <div className="sidebar-heading">
          <NavLink className="brand" to={me?.role === "admin" ? "/admin" : sponsor ? "/sponsor" : "/site"} onClick={closeMenu} aria-label="Phoenix Clinical home">
            <img className="brand-logo" src="/logo.png" alt="Phoenix Clinical Research" />
          </NavLink>
          {me && can("notifications.view") && <NotificationBell key={me.user.id} />}
          <button ref={toggleRef} type="button" className="sidebar-toggle" aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-expanded={menuOpen} aria-controls="workspace-navigation" onClick={() => setMenuOpen(!menuOpen)}>
            <SidebarIcon name={menuOpen ? "close" : "menu"} />
          </button>
        </div>

        <div className="sidebar-content" id="workspace-navigation">
          <nav className="nav" aria-label="Main" ref={navRef}>
            {id && <div>
              <section className="navigation-context" aria-label="Current workspace context" aria-busy={navigation.loading}>
                <p className="navigation-context-label">{sponsor ? "Selected protocol" : "Assigned eCRF"}</p>
                {navigation.loading && <p className="navigation-context-help" role="status">Loading details…</p>}
                {navigation.error && <><p className="navigation-context-help" role="status">Details unavailable. You can still use the workspace links below.</p><button className="navigation-context-retry" type="button" onClick={navigation.retry}>Retry details</button></>}
                {navigation.data && <>
                  <span className="navigation-context-study">{sponsor ? "Protocol" : "Assigned protocol"}</span>
                  <strong className="navigation-context-name">{navigation.data.protocol.name}</strong>
                  <span className="navigation-context-state">{navigation.data.protocol.state === "locked" ? "Locked eCRF" : navigation.data.protocol.state === "draft" ? "Draft eCRF" : "Not extracted yet"}</span>
                </>}
                <div className="navigation-context-links">
                  <Link to={sponsor ? "/sponsor/protocols" : "/site"} onClick={closeMenu}>{sponsor ? "← All protocols" : "← Change study"}</Link>
                </div>
              </section>
              {protocolItems.length > 0 && <div className="nav-protocol-tools"><div className="nav-group-label navigation-protocol-heading">{sponsor ? "Protocol tools" : "Hospital tools"}</div><SidebarLinks items={visible(protocolItems)} onNavigate={closeMenu} /></div>}
            </div>}
            <div className="nav-section">
              <div className="nav-group-label">Workspace</div>
              {sponsor && (
                <>
                  <SidebarLinks items={visible(dashboardItems)} onNavigate={closeMenu} />
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
              <SidebarLinks items={sponsor ? workspaceItems : visible(workspaceItems)} onNavigate={closeMenu} />
            </div>
          </nav>

          <div className="sidebar-foot">
            {me && (
              <div className="identity">
                <span className="identity-avatar" aria-hidden="true">{initials}</span>
                <details ref={accountRef} className="identity-account" onKeyDown={(event) => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); event.stopPropagation(); } }}>
                  <summary className="identity-details" aria-label={`Account options for ${me.user.name}`} title="Account options">
                    <span className="identity-user">{me.user.name}</span>
                    <span className="identity-org" title={me.org.name}>{ROLE_LABEL[me.role] ?? me.role} · {me.org.name}</span>
                  </summary>
                  <div className="identity-account-links"><Link to="/glossary">Glossary</Link><Link to="/change-password">Change password</Link></div>
                </details>
                <button type="button" className="identity-out" onClick={() => { const action = () => { void signOut(); }; if (leaveGuard.current) leaveGuard.current(action); else action(); }} aria-label="Sign out" title="Sign out">
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
