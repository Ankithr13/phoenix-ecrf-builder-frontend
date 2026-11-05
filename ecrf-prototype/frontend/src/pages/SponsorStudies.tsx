import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { SponsorStudy } from "../api/types";
import StudyForm from "../components/StudyForm";

export default function SponsorStudies() {
  const [studies, setStudies] = useState<SponsorStudy[]>([]);
  const [unassigned, setUnassigned] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [studyRows, protocolRows] = await Promise.all([
        api.sponsorStudies(), api.listProtocols({ unassigned: true }),
      ]);
      setStudies(studyRows);
      setUnassigned(protocolRows.length);
      setError(null);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const created = () => {
    setCreating(false);
    refresh();
  };
  const query = search.trim().toLowerCase();
  const visibleStudies = studies.filter((study) => `${study.name} ${study.code}`.toLowerCase().includes(query));

  return (
    <div className="page studies-page">
      <div className="page-head row row-between row-wrap">
        <div>
          <p className="study-eyebrow">Study workspace</p>
          <h1 className="page-title">Studies</h1>
          <p className="muted small">Organise protocols by study and keep each research programme together.</p>
        </div>
        <button className="btn btn-teal" type="button" onClick={() => setCreating(true)} disabled={creating}>+ Create study</button>
      </div>

      {creating && <StudyForm onCreated={created} onCancel={() => setCreating(false)} />}
      {error && <p className="error mt-3" role="alert">{error}</p>}
      {unassigned > 0 && (
        <div className="study-unassigned row row-between row-wrap mt-4">
          <div><strong>{unassigned} unassigned protocol{unassigned === 1 ? "" : "s"}</strong><p className="small muted">Existing protocols are preserved. Choose their studies when you are ready.</p></div>
          <Link className="btn btn-secondary btn-sm" to="/sponsor/protocols?unassigned=1">Assign protocols</Link>
        </div>
      )}

      <div className="row row-between row-wrap mt-5 mb-4">
        <span className="muted small">{studies.length} stud{studies.length === 1 ? "y" : "ies"} · {studies.reduce((total, study) => total + study.protocol_count, 0)} assigned protocols</span>
        <input className="input study-search" type="search" aria-label="Search studies" placeholder="Search by study name or ID" value={search} onChange={(event) => setSearch(event.target.value)} />
      </div>
      {loading && <p className="muted">Loading studies…</p>}
      {!loading && !error && studies.length === 0 && (
        <div className="empty"><h2 className="section-title">Your studies start here</h2><p>Create a study with its name and study ID. Add protocols using Upload Protocol in the sidebar.</p></div>
      )}
      {!loading && studies.length > 0 && visibleStudies.length === 0 && <div className="empty">No studies match your search.</div>}
      <div className="study-grid">
        {visibleStudies.map((study) => (
          <article className="card study-card" key={study.id}>
            <span className="study-code">{study.code}</span>
            <h2 className="section-title"><Link to={`/sponsor/studies/${study.id}`}>{study.name}</Link></h2>
            <p className="small muted">{study.protocol_count} protocol{study.protocol_count === 1 ? "" : "s"}</p>
            <Link className="study-open" to={`/sponsor/studies/${study.id}`}>Open study <span aria-hidden="true">→</span></Link>
          </article>
        ))}
      </div>
    </div>
  );
}
