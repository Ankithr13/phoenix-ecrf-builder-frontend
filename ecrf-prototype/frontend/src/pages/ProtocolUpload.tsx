import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { ProtocolUploadResult, SponsorStudy } from "../api/types";
import { useAuth } from "../auth/useAuth";
import StudyForm from "../components/StudyForm";
import "../styles/protocol-upload.css";

function uploadError(failure: unknown): string {
  if (failure instanceof ApiError) {
    if (failure.status === 401) return "Your session has expired. Sign in again before uploading.";
    if (failure.status === 403) return "You do not have permission to upload protocols. Ask your administrator for access.";
    if (failure.status === 404) return "The selected study is no longer available. Refresh the study list and choose a study again.";
    if (failure.status === 409) return "This protocol already belongs to another study. It has not been moved. Check All protocols to review or change its assignment.";
    if (failure.status === 413) return "The server could not accept a file this large. Choose a smaller PDF or ask your administrator about the upload limit.";
    if (failure.status === 400) return "This file could not be accepted. Choose a readable protocol PDF with a .pdf filename.";
    if (failure.status === 422) return typeof failure.detail === "string"
      ? `${failure.detail} Choose a readable, text-based PDF and try again.`
      : "The file or study could not be accepted. Check your study selection and choose a readable, text-based PDF.";
  }
  return "We could not confirm the upload. Check your connection and All protocols before trying again. Your selection is kept here; retrying the same PDF will not create a duplicate protocol.";
}

function fileSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.ceil(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ProtocolUpload() {
  const { can } = useAuth();
  const [studies, setStudies] = useState<SponsorStudy[]>([]);
  const [studyId, setStudyId] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [studyError, setStudyError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{ file: File; url: string } | null>(null);
  const [uploaded, setUploaded] = useState<ProtocolUploadResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const successRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setStudyError(false);
    api.sponsorStudies().then((rows) => {
      if (!active) return;
      setStudies(rows);
      setStudyId((previous) => rows.some((study) => String(study.id) === previous) ? previous : "");
    }).catch(() => {
      if (active) setStudyError(true);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [loadAttempt]);

  useEffect(() => {
    if (!selectedFile) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(selectedFile);
    setPreview({ file: selectedFile, url });
    return () => URL.revokeObjectURL(url);
  }, [selectedFile]);

  useEffect(() => {
    if (uploaded) successRef.current?.focus();
  }, [uploaded]);

  const clearSelection = () => {
    setSelectedFile(null);
    setError(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const created = (study: SponsorStudy) => {
    setStudies((previous) => [...previous, study].sort((first, second) => first.name.localeCompare(second.name)));
    setStudyId(String(study.id));
    setSearch("");
    setCreating(false);
    setUploaded(null);
    setError(null);
  };
  const selectedStudy = studies.find((study) => String(study.id) === studyId);
  const upload = async () => {
    if (!selectedStudy || !selectedFile || inFlight.current || loading || studyError || creating || !can("protocol.upload")) return;
    inFlight.current = true;
    setBusy(true);
    setUploaded(null);
    setError(null);
    try {
      const result = await api.upload(selectedFile, selectedStudy.id);
      setUploaded(result);
      clearSelection();
    } catch (failure) {
      setError(uploadError(failure));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  const pickFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploaded(null);
    setSelectedFile(null);
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      event.target.value = "";
      setError("Choose a protocol PDF with a .pdf filename. No file has been uploaded.");
    } else if (file.size === 0) {
      event.target.value = "";
      setError("This PDF is empty. Choose a file with content. No file has been uploaded.");
    } else {
      setError(null);
      setSelectedFile(file);
    }
  };
  const query = search.trim().toLowerCase();
  const visibleStudies = studies.filter((study) => String(study.id) === studyId || `${study.name} ${study.code}`.toLowerCase().includes(query));
  const uploadedStudy = studies.find((study) => study.id === uploaded?.study_id);
  const previewUrl = preview?.file === selectedFile ? preview?.url : null;
  const disabled = busy || loading || studyError || creating || !can("protocol.upload");

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Upload Protocol</h1>
        <p className="muted small">Choose a study and PDF, review both, then confirm the upload.</p>
      </div>
      {!can("protocol.upload") && <p className="error mb-4" role="alert">You do not have permission to upload protocols.</p>}
      <section className="card">
        <div className="row row-between row-wrap mb-4">
          <h2 className="section-title" style={{ marginBottom: 0 }}>1. Choose a study</h2>
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => setCreating(true)} disabled={disabled}>+ Create new study</button>
        </div>
        {loading && <p className="muted small">Loading studies…</p>}
        {studyError && <div role="alert" className="stack-sm"><p className="error">We could not load your studies. Retry before uploading.</p><button type="button" className="btn btn-secondary" onClick={() => setLoadAttempt((previous) => previous + 1)}>Retry loading studies</button></div>}
        {!loading && !studyError && studies.length === 0 && <p className="muted small">Create your first study to enable protocol uploads.</p>}
        {studies.length > 0 && (
          <div className="stack-sm">
            <input className="input" type="search" aria-label="Search study options" placeholder="Search by study name or ID" value={search} onChange={(event) => setSearch(event.target.value)} disabled={disabled} />
            <label className="label" htmlFor="upload-study">Study <span className="req">*</span></label>
            <select className="input" id="upload-study" value={studyId} onChange={(event) => { setStudyId(event.target.value); setUploaded(null); setError(null); }} disabled={disabled} required>
              <option value="">Select a study</option>
              {visibleStudies.map((study) => <option key={study.id} value={study.id}>{study.code} · {study.name}</option>)}
            </select>
            {visibleStudies.length === 0 && <p className="muted small">No matching studies. Try another search or create a study.</p>}
            <button className="btn btn-secondary btn-sm upload-refresh" type="button" disabled={disabled} onClick={() => { setError(null); setLoadAttempt((previous) => previous + 1); }}>Refresh study list</button>
          </div>
        )}
      </section>
      {creating && <div className="mt-4"><StudyForm onCreated={created} onCancel={() => setCreating(false)} /></div>}
      <section className="card">
        <h2 className="section-title">2. Choose the protocol PDF</h2>
        <p className="muted small mb-4">Use a text-based PDF. Scanned images are not supported. Choosing a file does not upload it.</p>
        {!studyId && <p className="muted small mb-4">Select a study above to choose a file.</p>}
        <div className="upload-picker">
          <input ref={fileRef} type="file" aria-label="Choose a protocol PDF" accept="application/pdf,.pdf" onChange={pickFile} disabled={!selectedStudy || disabled} />
        </div>
      </section>
      {selectedFile && (
        <section className="card" aria-labelledby="upload-review-title" aria-busy={busy}>
          <h2 id="upload-review-title" className="section-title">3. Review before uploading</h2>
          <dl className="upload-summary">
            <div><dt>Study ID</dt><dd>{selectedStudy?.code || "Select a study above"}</dd></div>
            <div><dt>Study name</dt><dd>{selectedStudy?.name || "No study selected"}</dd></div>
            <div><dt>Protocol file</dt><dd>{selectedFile.name}</dd></div>
            <div><dt>File size</dt><dd>{fileSize(selectedFile.size)}</dd></div>
          </dl>
          {previewUrl && (
            <div className="upload-preview">
              <iframe title={`Local PDF preview: ${selectedFile.name}`} src={previewUrl} />
              <p className="upload-preview-note">Preview only — not uploaded yet. If the PDF does not display, <a href={previewUrl} target="_blank" rel="noreferrer">open the selected PDF in a new tab</a> or inspect it on your computer.</p>
            </div>
          )}
          <p className="muted small mt-4">Check that the protocol belongs to this study. The app does not automatically infer its study from the document. File selections are not kept if you leave this page.</p>
          <div className="row row-wrap upload-actions">
            <button className="btn btn-teal" type="button" onClick={() => void upload()} disabled={!selectedStudy || disabled}>{busy ? "Adding protocol…" : "Confirm and upload protocol"}</button>
            <button className="btn btn-secondary" type="button" onClick={clearSelection} disabled={busy}>Cancel selection</button>
          </div>
          {busy && <p className="muted small mt-4" role="status">Uploading and reading the PDF. Keep this page open until it finishes.</p>}
        </section>
      )}
      {error && <div className="upload-feedback" role="alert"><p className="error">{error}</p><p className="small mt-2">{selectedFile ? "Your selection is still available above. Check it, choose a different file or study, or confirm again to retry." : "Choose a PDF above to continue."}</p><Link className="small" to="/sponsor/protocols">Check All protocols</Link></div>}
      {uploaded && !busy && (
        <div ref={successRef} className="card mt-4 upload-success" role="status" tabIndex={-1}>
          <p className="strong">{uploaded.already_loaded ? "Protocol already in your workspace" : "Protocol added"}</p>
          <p className="muted small mt-2">{uploaded.name}{uploadedStudy && <> · {uploadedStudy.code}</>}</p>
          {uploaded.already_loaded && <p className="muted small mt-2">The existing protocol is being used. No duplicate was created.</p>}
          <div className="row row-wrap mt-4">
            {can("protocol.extract") && <Link className="btn btn-teal" to={`/sponsor/p/${uploaded.id}/visits`}>Continue to extraction</Link>}
            {uploaded.study_id && <Link className="btn btn-secondary" to={`/sponsor/studies/${uploaded.study_id}`}>View study protocols</Link>}
          </div>
        </div>
      )}
    </div>
  );
}
