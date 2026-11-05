import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ProtocolUploadResult, SponsorStudy } from "../api/types";
import { useAuth } from "../auth/useAuth";
import StudyForm from "../components/StudyForm";

export default function ProtocolUpload() {
  const { can } = useAuth();
  const [studies, setStudies] = useState<SponsorStudy[]>([]);
  const [studyId, setStudyId] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<ProtocolUploadResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.sponsorStudies().then(setStudies).catch((failure) => setError((failure as Error).message)).finally(() => setLoading(false));
  }, []);

  const created = (study: SponsorStudy) => {
    setStudies((previous) => [...previous, study].sort((first, second) => first.name.localeCompare(second.name)));
    setStudyId(String(study.id));
    setSearch("");
    setCreating(false);
    setUploaded(null);
  };
  const upload = async (file?: File) => {
    if (!studyId || !can("protocol.upload")) return;
    setBusy(true);
    setUploaded(null);
    setError(null);
    try {
      setUploaded(file ? await api.upload(file, Number(studyId)) : await api.loadSample(Number(studyId)));
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };
  const pickFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) upload(file);
  };
  const query = search.trim().toLowerCase();
  const visibleStudies = studies.filter((study) => String(study.id) === studyId || `${study.name} ${study.code}`.toLowerCase().includes(query));
  const uploadedStudy = studies.find((study) => study.id === uploaded?.study_id);

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Upload Protocol</h1>
        <p className="muted small">Choose the study this protocol belongs to, then upload its PDF.</p>
      </div>
      {error && <p className="error mb-4" role="alert">{error}</p>}
      <section className="card">
        <div className="row row-between row-wrap mb-4">
          <h2 className="section-title" style={{ marginBottom: 0 }}>1. Choose a study</h2>
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => setCreating(true)} disabled={busy || creating || loading}>+ Create new study</button>
        </div>
        {loading && <p className="muted small">Loading studies…</p>}
        {!loading && studies.length === 0 && <p className="muted small">Create your first study to enable protocol uploads.</p>}
        {studies.length > 0 && (
          <div className="stack-sm">
            <input className="input" type="search" aria-label="Search study options" placeholder="Search by study name or ID" value={search} onChange={(event) => setSearch(event.target.value)} disabled={busy} />
            <label className="label" htmlFor="upload-study">Study <span className="req">*</span></label>
            <select className="input" id="upload-study" value={studyId} onChange={(event) => { setStudyId(event.target.value); setUploaded(null); setError(null); }} disabled={busy} required>
              <option value="">Select a study</option>
              {visibleStudies.map((study) => <option key={study.id} value={study.id}>{study.code} · {study.name}</option>)}
            </select>
            {visibleStudies.length === 0 && <p className="muted small">No matching studies. Try another search or create a study.</p>}
          </div>
        )}
      </section>
      {creating && <div className="mt-4"><StudyForm onCreated={created} onCancel={() => setCreating(false)} /></div>}
      <section className="card">
        <h2 className="section-title">2. Add the protocol PDF</h2>
        {!studyId && <p className="muted small mb-4">Select a study above to enable these options.</p>}
        <div className="row row-wrap">
          <label className={`drop${!studyId || busy ? " drop-disabled" : ""}`}>
            <input ref={fileRef} type="file" accept="application/pdf,.pdf" onChange={pickFile} disabled={!studyId || busy || !can("protocol.upload")} />
            {busy ? "Adding protocol…" : "Choose a protocol PDF"}
          </label>
          <button className="btn btn-secondary" type="button" onClick={() => upload()} disabled={!studyId || busy || !can("protocol.upload")}>Load sample protocol</button>
        </div>
      </section>
      {uploaded && !busy && (
        <div className="card mt-4" role="status">
          <p className="strong">{uploaded.already_loaded ? "Protocol already in your workspace" : "Protocol added"}</p>
          <p className="muted small mt-2">{uploaded.name}{uploadedStudy && <> · {uploadedStudy.code}</>}</p>
          <div className="row row-wrap mt-4">
            {can("protocol.extract") && <Link className="btn btn-teal" to={`/sponsor/p/${uploaded.id}/visits`}>Continue to extraction</Link>}
            {uploaded.study_id && <Link className="btn btn-secondary" to={`/sponsor/studies/${uploaded.study_id}`}>View study protocols</Link>}
          </div>
        </div>
      )}
    </div>
  );
}
