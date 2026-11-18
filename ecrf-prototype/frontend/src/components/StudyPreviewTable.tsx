import { Link } from "react-router-dom";
import { STUDY_FILTERS } from "../workspace/studyPresentation";

export default function StudyPreviewTable({ filter, onFilter, recent = true }: { filter: string; onFilter: (value: string) => void; recent?: boolean }) {
  return <section className="workspace-study-panel" aria-labelledby="workspace-studies-title">
    <div className="workspace-panel-heading"><div><h2 id="workspace-studies-title">{recent ? "Recent studies" : "All studies"}</h2><p>Your newest studies and protocol updates, in one place.</p></div>{recent ? <Link to="/sponsor/studies">View all studies <span aria-hidden="true">→</span></Link> : <span className="pill">Backend pending</span>}</div>
    <div className="workspace-filters" role="group" aria-label="Filter studies">{STUDY_FILTERS.map((item) => <button key={item.value} type="button" aria-pressed={filter === item.value} className={filter === item.value ? "selected" : ""} onClick={() => onFilter(item.value)}>{item.label}<span aria-label="Count unavailable">—</span></button>)}</div>
    <div className="workspace-table-wrap"><table className="workspace-table"><caption className="workspace-visually-hidden">Study grouping placeholder. No study records are loaded.</caption>
      <thead><tr><th scope="col">Study name</th><th scope="col">Study ID</th><th scope="col">Protocols</th><th scope="col">Form status</th><th scope="col">Latest protocol update</th><th scope="col" className="workspace-table-action">Action</th></tr></thead>
      <tbody><tr><td colSpan={6}><div className="workspace-empty"><h3>Study data not connected</h3><p>Study records and counts will appear here when study grouping is connected.</p><Link className="btn btn-secondary btn-sm" to="/sponsor/protocols">View protocol documents</Link></div></td></tr></tbody>
    </table></div>
  </section>;
}
