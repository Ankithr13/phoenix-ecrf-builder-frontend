import { Link, useSearchParams } from "react-router-dom";
import StudyCreationPlaceholder from "../components/StudyCreationPlaceholder";

export default function StudyWorkspace() {
  const [params, setParams] = useSearchParams();
  const creating = params.get("create") === "1";
  const setCreating = (value: boolean) => setParams(value ? { create: "1" } : {}, { replace: true });
  return <div className="page studies-page">
    <div className="page-head row row-between row-wrap">
      <div><p className="study-eyebrow">Study workspace</p><h1 className="page-title">Studies</h1><p className="muted small">Organise protocols by study and keep each research programme together.</p></div>
      <button className="btn btn-teal" type="button" onClick={() => setCreating(true)} disabled={creating}>+ Create study</button>
    </div>
    {creating && <StudyCreationPlaceholder onClose={() => setCreating(false)} />}
    <div className="row row-between row-wrap mt-5 mb-4">
      <span className="muted small">— studies · — assigned protocols</span>
      <input className="input study-search" type="search" aria-label="Search studies" placeholder="Search by study name or ID" disabled />
    </div>
    <div className="empty"><h2 className="section-title">Study data not connected</h2><p>No study records or sample data are displayed. Study creation and protocol assignment will be available when connected.</p><p className="mt-4"><Link className="btn btn-secondary btn-sm" to="/sponsor/protocols">View protocol documents</Link></p></div>
    <div className="study-grid" />
  </div>;
}
