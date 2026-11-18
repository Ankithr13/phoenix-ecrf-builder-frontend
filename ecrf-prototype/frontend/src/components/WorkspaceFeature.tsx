import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

type Feature = "upload" | "status" | "clinical" | "queries" | "reports";
const FEATURES: Record<Feature, { title: string; description: string; permissions: string[]; columns: string[] }> = {
  upload: { title: "Upload Protocol", description: "Select a protocol PDF, preview it, then proceed to extraction.", permissions: ["protocol.upload"], columns: [] },
  status: { title: "eCRF Status", description: "Track hospital updates, patient visits and submitted forms in one place.", permissions: ["dashboard.subject_level"], columns: ["Hospital", "Study", "Patients", "Current visit", "Form status", "Last update"] },
  clinical: { title: "Clinical Data Review", description: "Verify the answers hospitals have submitted and request corrections when needed.", permissions: ["listing.view"], columns: ["Hospital", "Patient", "Visit", "Submission status", "Submitted", "Action"] },
  queries: { title: "Queries", description: "Follow questions, responses and requests for clarification.", permissions: ["query.raise", "query.answer", "query.close"], columns: ["Study", "Hospital", "Query", "Status", "Last update", "Action"] },
  reports: { title: "Analytics & Reports", description: "Open permitted study reports and analysis results.", permissions: ["dashboard.view"], columns: ["Study", "Report", "Status", "Updated", "Action"] },
};

export default function WorkspaceFeature({ feature, children, preview }: { feature: Feature; children: ReactNode; preview?: ReactNode }) {
  const { can } = useAuth();
  const definition = FEATURES[feature];
  if (definition.permissions.some((permission) => can(permission))) return children;
  if (preview) return preview;
  return <div className="page feature-preview">
    <div className="page-head"><h1 className="page-title">{definition.title}</h1><p className="muted small">{definition.description}</p></div>
    <div className="feature-preview-notice" role="note"><span className="pill chip-amber">Layout preview</span><p>This section is kept in the workspace design. Your current role cannot access its live data or actions. No protected records are loaded and no permissions have been changed.</p></div>
    <section className="workspace-study-panel">
      <div className="workspace-panel-heading"><div><h2>{definition.title}</h2><p>Empty preview — no sample records</p></div><span className="pill">Awaiting authorized access</span></div>
      <div className="feature-preview-filters"><input className="input" aria-label={`Search ${definition.title} (preview)`} placeholder="Search…" disabled /><select className="input" aria-label="Status (preview)" disabled><option>All statuses</option></select></div>
      <div className="workspace-table-wrap"><table className="workspace-table"><caption className="workspace-visually-hidden">Empty {definition.title} layout preview</caption><thead><tr>{definition.columns.map((column) => <th key={column} scope="col">{column}</th>)}</tr></thead><tbody><tr><td colSpan={definition.columns.length} className="feature-preview-empty">Records will appear here when this section is connected and authorized for your role.</td></tr></tbody></table></div>
    </section>
    <p className="muted small mt-4"><Link to="/sponsor">← Back to dashboard</Link></p>
  </div>;
}
