import { Link, Navigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { useWorkspaceOverview, type WorkspaceCounts } from "../hooks/useWorkspaceOverview";
import StudyPreviewTable from "../components/StudyPreviewTable";
import { STUDY_FILTERS } from "../workspace/studyPresentation";
import Icon, { type IconName } from "../components/Icon";
import NavigationActions from "../components/NavigationActions";
import "../styles/workspace.css";

const METRICS: { key: keyof WorkspaceCounts; label: string; note: string; icon: IconName; tone: string; to: string }[] = [
  { key: "studies", label: "Total studies", note: "Studies in your organisation", icon: "protocols", tone: "blue", to: "/sponsor/studies" },
  { key: "protocols", label: "Protocol documents", note: "Protocol documents in your workspace", icon: "forms", tone: "teal", to: "/sponsor/protocols" },
  { key: "pending_reviews", label: "Pending eCRF reviews", note: "Protocols awaiting form review or lock", icon: "visits", tone: "amber", to: "/sponsor/ecrfs?stage=draft" },
  { key: "queries_for_me", label: "Queries needing you", note: "Your organisation’s turn to respond", icon: "queries", tone: "blue", to: "/sponsor/queries" },
];

export default function WorkspaceDashboard() {
  const { me, can } = useAuth();
  const { overview, refreshing, error, refresh } = useWorkspaceOverview();
  const [params, setParams] = useSearchParams();
  const search = params.get("search") ?? "";
  const filter = STUDY_FILTERS.find((item) => item.value === params.get("stage"))?.value ?? "all";
  const update = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value && value !== "all") next.set(name, value); else next.delete(name);
    setParams(next, { replace: true });
  };
  if (!can("dashboard.view")) return <Navigate to={me?.org.type === "site" ? "/site" : "/sponsor/protocols"} replace />;
  const today = new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

  return (
    <div className="workspace-dashboard">
      <NavigationActions>
        <div className="workspace-tools">
          <label className="workspace-search"><Icon name="search" className="workspace-icon" /><input type="search" aria-label="Search dashboard studies" placeholder="Search studies…" value={search} onChange={(event) => update("search", event.target.value)} /></label>
          <button className="workspace-refresh" type="button" onClick={refresh} disabled={refreshing} aria-label="Refresh dashboard" title="Refresh dashboard"><Icon name="refresh" className="workspace-icon" /></button>
        </div>
      </NavigationActions>
      <div className="workspace-body" aria-busy={refreshing}>
        <div className="workspace-heading">
          <div><p className="study-eyebrow"><span aria-hidden="true">●</span> Workspace overview</p><h1>Study overview</h1><p>Track your studies, review protocols, and follow up on the work that needs you.</p></div>
          <div className="workspace-actions"><span className="workspace-date"><Icon name="visits" className="workspace-icon" />{today}</span><Link className="workspace-create" to="/sponsor/studies?create=1"><span aria-hidden="true">+</span> Create new study</Link></div>
        </div>
        {error && <div className="workspace-error" role="alert"><strong>Couldn’t load your overview.</strong><p>{error}</p><button type="button" className="btn btn-secondary btn-sm mt-3" onClick={refresh} disabled={refreshing}>Try again</button></div>}
        <div className="workspace-metrics">
          {METRICS.map((metric) => (
            <Link className="workspace-metric" to={metric.to} key={metric.key}>
              <div className="workspace-metric-heading"><span>{metric.label}</span><span className={`workspace-metric-icon ${metric.tone}`}><Icon name={metric.icon} className="workspace-icon" /></span></div>
              <strong className="workspace-metric-value">{overview?.counts[metric.key]?.toLocaleString() ?? "—"}</strong>
              <span className="workspace-metric-note">{metric.note}</span>
            </Link>
          ))}
        </div>
        <StudyPreviewTable filter={filter} onFilter={(value) => update("stage", value)} />
        {overview && <div className="workspace-footer"><span>{overview.counts.locked_protocols} protocol{overview.counts.locked_protocols === 1 ? " has" : "s have"} locked forms · {overview.counts.unextracted_protocols} awaiting extraction</span><Link to="/sponsor/upload"><Icon name="upload" className="workspace-icon" />Upload Protocol</Link></div>}
      </div>
    </div>
  );
}
