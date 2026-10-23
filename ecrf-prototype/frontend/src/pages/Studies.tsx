import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { StudyListItem } from "../api/types";
import { useAuth } from "../auth/useAuth";

/* The site portal's home: studies this site has been assigned to. A study
   appears here only once the sponsor has locked the form and assigned the
   site, which arrives in stage 3; until then the list is honest and empty. */
export default function Studies() {
  const { me } = useAuth();
  const [items, setItems] = useState<StudyListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.studies().then(setItems).catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Studies</h1>
        <div className="muted small">{me?.org.name} · site code {me?.org.code}</div>
      </div>
      {error && <p className="error">{error}</p>}
      {items === null && !error && <p className="muted">Loading…</p>}
      {items && items.length === 0 && (
        <div className="card">
          <p className="strong">No studies assigned yet</p>
          <p className="muted small mt-2">
            A study appears here once its sponsor has locked the eCRF and assigned this site to it.
          </p>
        </div>
      )}
      {items && items.map((s) => (
        <div className="card card-hover" key={s.id}>
          <div className="row row-between">
            <div>
              <div className="strong">{s.name}</div>
              <div className="muted small">{s.pages} pages</div>
            </div>
            <Link className="btn btn-primary btn-sm" to={`/site/s/${s.id}/data`}>Enter data</Link>
          </div>
        </div>
      ))}
    </div>
  );
}
