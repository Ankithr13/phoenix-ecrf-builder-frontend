import { useContext } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { NavigationContext } from "../navigation/context";
import Icon from "./Icon";

const PAGES: Record<string, string> = {
  "/sponsor": "Dashboard", "/sponsor/studies": "Studies", "/sponsor/protocols": "All protocols",
  "/sponsor/upload": "Upload Protocol", "/sponsor/ecrfs": "eCRF Management",
  "/sponsor/ecrf-status": "eCRF Status", "/sponsor/data": "Clinical Data Review",
  "/sponsor/reports": "Analytics & Reports", "/sponsor/queries": "Queries",
  "/notifications": "Notifications", "/admin": "Admin", "/change-password": "Change password", "/glossary": "Glossary", "/site": "Studies", "/site/queries": "Queries",
};

const SECTIONS: Record<string, string> = {
  visits: "Visits & extraction", review: "eCRF Review", sites: "Sites",
  data: "Data review", dashboard: "Reports", patients: "Patients", entry: "Data entry", listing: "Data listing",
};

export default function NavigationBreadcrumbs() {
  const context = useContext(NavigationContext);
  const { me } = useAuth();
  const { pathname } = useLocation();
  const sponsor = me?.org.type === "sponsor";
  const home = me?.role === "admin" ? "/admin" : sponsor ? "/sponsor" : "/site";
  const crumbs: { label: string; to?: string }[] = [{ label: sponsor ? "Workspace" : "Hospital workspace", to: home }];
  if (context?.protocolId) {
    if (sponsor) crumbs.push({ label: "Protocols", to: "/sponsor/protocols" });

    const protocolLabel = context.data?.protocol.name ?? (context.error ? "Protocol unavailable" : "Loading protocol…");
    crumbs.push({ label: protocolLabel });
    if (context.section === "entry") {
      crumbs.push({ label: "Patients", to: `/site/s/${context.protocolId}/patients` });
    }
    crumbs.push({ label: SECTIONS[context.section ?? ""] ?? "Protocol workspace" });
  } else {
    crumbs.push({ label: PAGES[pathname] ?? "Workspace" });
  }
  return <nav className="navigation-breadcrumb" aria-label="Breadcrumb"><ol>{crumbs.map((crumb, index) => <li key={`${index}-${crumb.label}`}>
    {index > 0 && <Icon name="chevron" className="navigation-chevron" />}
    {crumb.to && index < crumbs.length - 1 ? <Link to={crumb.to} title={crumb.label}>{crumb.label}</Link> : <span aria-current={index === crumbs.length - 1 ? "page" : undefined} title={crumb.label}>{crumb.label}</span>}
  </li>)}</ol></nav>;
}
