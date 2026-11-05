import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { StudyProgress, WorkspaceOverview } from "../api/types";
import Icon, { type IconName } from "../components/Icon";
import NavigationActions from "../components/NavigationActions";
import "../styles/workspace.css";

const STATUS_LABELS: Record<StudyProgress, string> = {
  no_protocols: "No protocols",
  needs_extraction: "Needs extraction",
  needs_review: "Needs review",
  forms_locked: "Forms locked",
};

const METRICS: { key: keyof WorkspaceOverview["counts"]; label: string; note: string; icon: IconName; tone: string; to: string }[] = [
  { key: "studies", label: "Total studies", note: "Studies in your organisation", icon: "protocols", tone: "blue", to: "/sponsor/studies" },
  { key: "protocols", label: "Protocol documents", note: "Across all studies, including unassigned", icon: "forms", tone: "teal", to: "/sponsor/protocols" },
  { key: "pending_reviews", label: "Pending eCRF reviews", note: "Protocols awaiting form review or lock", icon: "visits", tone: "amber", to: "/sponsor/ecrfs?pending=1" },
  { key: "queries_for_me", label: "Queries needing you", note: "Your organisation’s turn to respond", icon: "queries", tone: "blue", to: "/sponsor/queries" },
];

type StudyFilter = "all" | "needs_review" | "needs_extraction" | "forms_locked";

const FILTERS: { value: StudyFilter; label: string }[] = [
  { value: "all", label: "All studies" },
  { value: "needs_review", label: "Needs review" },
  { value: "needs_extraction", label: "Needs extraction" },
  { value: "forms_locked", label: "Forms locked" },
];

export default function WorkspaceDashboard() {
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [refreshing, setRefreshing] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<StudyFilter>("all");

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setOverview(await api.workspaceDashboard());
      setError(null);
    } catch (failure) {
      setError((failure as Error).message);
      setOverview(null);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const query = search.trim().toLowerCase();
  const studies = overview?.studies ?? [];
  const visibleStudies = studies.filter((study) =>
    (filter === "all" || study.status === filter) && `${study.name} ${study.code}`.toLowerCase().includes(query));
  const today = new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

  return (
    <div className="workspace-dashboard">
      <NavigationActions>
        <div className="workspace-tools">
          <label className="workspace-search"><Icon name="search" className="workspace-icon" /><input type="search" aria-label="Search dashboard studies" placeholder="Search studies…" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
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
              <strong className="workspace-metric-value">{overview ? overview.counts[metric.key].toLocaleString() : "—"}</strong>
              <span className="workspace-metric-note">{metric.note}</span>
            </Link>
          ))}
        </div>
        {overview && overview.counts.unassigned_protocols > 0 && (
          <div className="workspace-assignment-notice"><div><strong>{overview.counts.unassigned_protocols} protocol{overview.counts.unassigned_protocols === 1 ? " needs" : "s need"} a study</strong><p>Assign existing documents so they appear in the right study workspace.</p></div><Link to="/sponsor/protocols?unassigned=1">Assign protocols <span aria-hidden="true">→</span></Link></div>
        )}
        <section className="workspace-study-panel" aria-labelledby="workspace-studies-title">
          <div className="workspace-panel-heading"><div><h2 id="workspace-studies-title">Recent studies</h2><p>Your newest studies and protocol updates, in one place.</p></div><Link to="/sponsor/studies">View all studies <span aria-hidden="true">→</span></Link></div>
          <div className="workspace-filters" role="group" aria-label="Filter dashboard studies">
            {FILTERS.map((item) => <button key={item.value} type="button" aria-pressed={filter === item.value} className={filter === item.value ? "selected" : ""} onClick={() => setFilter(item.value)}>{item.label}<span>{studies.filter((study) => item.value === "all" || study.status === item.value).length}</span></button>)}
          </div>
          {refreshing && !overview && !error && <p className="workspace-empty" role="status">Loading your workspace…</p>}
          {overview && studies.length === 0 && <div className="workspace-empty"><h3>Create your first study</h3><p>Give your research a name and study ID, then add its protocols from Upload Protocol.</p><Link className="workspace-create" to="/sponsor/studies?create=1">+ Create a study</Link></div>}
          {overview && studies.length > 0 && visibleStudies.length === 0 && <div className="workspace-empty"><h3>No matching studies</h3><p>Try another search or choose a different status filter.</p><button className="btn btn-secondary btn-sm" type="button" onClick={() => { setSearch(""); setFilter("all"); }}>Clear filters</button></div>}
          {overview && visibleStudies.length > 0 && (
            <div className="workspace-table-wrap">
              <table className="workspace-table">
                <caption className="workspace-visually-hidden">Studies and their protocol form progress</caption>
                <thead><tr><th scope="col">Study name</th><th scope="col">Study ID</th><th scope="col">Protocols</th><th scope="col">Form status</th><th scope="col">Latest protocol update</th><th scope="col" className="workspace-table-action">Action</th></tr></thead>
                <tbody>{visibleStudies.map((study) => (
                  <tr key={study.id}>
                    <th scope="row"><div className="workspace-study-name"><span className="workspace-study-symbol"><Icon name="protocols" className="workspace-icon" /></span><Link to={`/sponsor/studies/${study.id}`}>{study.name}</Link></div></th>
                    <td className="workspace-study-code">{study.code}</td>
                    <td><strong>{study.protocol_count}</strong><span className="workspace-cell-note">{study.protocol_count ? `${study.locked_protocols} of ${study.protocol_count} locked` : "No forms yet"}</span></td>
                    <td><span className={`workspace-status ${study.status}`}><span aria-hidden="true">●</span>{STATUS_LABELS[study.status]}</span></td>
                    <td>{study.latest_protocol_update ? new Date(study.latest_protocol_update).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "No protocols yet"}</td>
                    <td className="workspace-table-action"><Link to={`/sponsor/studies/${study.id}`}>View study <span aria-hidden="true">›</span></Link></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </section>
        {overview && <div className="workspace-footer"><span>{overview.counts.locked_protocols} protocol{overview.counts.locked_protocols === 1 ? " has" : "s have"} locked forms · {overview.counts.unextracted_protocols} awaiting extraction</span><Link to="/sponsor/upload"><Icon name="upload" className="workspace-icon" />Upload Protocol</Link></div>}
      </div>
    </div>
  );
}
