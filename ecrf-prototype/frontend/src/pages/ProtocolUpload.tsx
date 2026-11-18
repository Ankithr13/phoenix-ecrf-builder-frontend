import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
type ProtocolUploadResult = Awaited<ReturnType<typeof api.upload>>;
import { useAuth } from "../auth/useAuth";
import "../styles/protocol-upload.css";

function uploadError(failure: unknown): string {
  if (failure instanceof ApiError) {
    if (failure.status === 401) return "Your session has expired. Sign in again before uploading.";
    if (failure.status === 403) return "You do not have permission to upload protocols. Ask your administrator for access.";
    if (failure.status === 413) return "The server could not accept a file this large. Choose a smaller PDF or ask your administrator about the upload limit.";
    if (failure.status === 400) return "This file could not be accepted. Choose a readable protocol PDF with a .pdf filename.";
    if (failure.status === 422) return typeof failure.detail === "string"
      ? `${failure.detail} Choose a readable, text-based PDF and try again.`
      : "The file or study could not be accepted. Choose a readable, text-based PDF.";
  }
  return "We could not confirm the upload. Check your connection and All protocols before trying again. Your selection is kept here; retrying the same PDF will not create a duplicate protocol.";
}

function fileSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.ceil(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ProtocolUpload({ previewOnly = false }: { previewOnly?: boolean }) {
  const { can } = useAuth();
  const allowed = !previewOnly && can("protocol.upload");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{ file: File; url: string } | null>(null);
  const [uploaded, setUploaded] = useState<ProtocolUploadResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const successRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false);


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

  const upload = async () => {
    if (!selectedFile || inFlight.current || !allowed) return;
    inFlight.current = true;
    setBusy(true);
    setUploaded(null);
    setError(null);
    try {
      const result = await api.upload(selectedFile);
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
  const previewUrl = preview?.file === selectedFile ? preview?.url : null;
  const disabled = busy || !allowed;

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Upload Protocol</h1>
        <p className="muted small">Choose your protocol PDF, preview it, then confirm the upload.</p>
      </div>
      {!allowed && <div className="feature-preview-notice" role="note"><span className="pill chip-amber">Layout preview</span><p>Uploading requires an authorized Builder. No protected records are loaded and no file can be selected or uploaded here.</p></div>}
      <section className="card">
        <div className="row row-between row-wrap mb-4"><h2 className="section-title" style={{ marginBottom: 0 }}>1. Study assignment</h2><button className="btn btn-secondary btn-sm" type="button" disabled>+ Create new study</button></div>
        <label className="label" htmlFor="upload-study">Study</label>
        <select className="input" id="upload-study" disabled><option>Study assignment not connected</option></select>
        <p className="muted small mt-3">Study assignment will be available later. You can upload a protocol without selecting a study.</p>
      </section>
      <section className="card">
        <h2 className="section-title">2. Choose the protocol PDF</h2>
        <p className="muted small mb-4">Use a text-based PDF. Scanned images are not supported. Choosing a file does not upload it.</p>
        <div className="upload-picker">
          <input ref={fileRef} type="file" aria-label="Choose a protocol PDF" accept="application/pdf,.pdf" onChange={pickFile} disabled={disabled} />
        </div>
      </section>
      {selectedFile && (
        <section className="card" aria-labelledby="upload-review-title" aria-busy={busy}>
          <h2 id="upload-review-title" className="section-title">3. Review before uploading</h2>
          <dl className="upload-summary">
            <div><dt>Study ID</dt><dd>{"—"}</dd></div>
            <div><dt>Study name</dt><dd>{"Not assigned"}</dd></div>
            <div><dt>Protocol file</dt><dd>{selectedFile.name}</dd></div>
            <div><dt>File size</dt><dd>{fileSize(selectedFile.size)}</dd></div>
          </dl>
          {previewUrl && (
            <div className="upload-preview">
              <iframe title={`Local PDF preview: ${selectedFile.name}`} src={previewUrl} />
              <p className="upload-preview-note">Preview only — not uploaded yet. If the PDF does not display, <a href={previewUrl} target="_blank" rel="noreferrer">open the selected PDF in a new tab</a> or inspect it on your computer.</p>
            </div>
          )}
          <p className="muted small mt-4">Check that this is the correct protocol. Extraction starts after upload, when you choose to continue. File selections are not kept if you leave this page.</p>
          <div className="row row-wrap upload-actions">
            <button className="btn btn-teal" type="button" onClick={() => void upload()} disabled={disabled}>{busy ? "Adding protocol…" : "Confirm and upload protocol"}</button>
            <button className="btn btn-secondary" type="button" onClick={clearSelection} disabled={busy}>Cancel selection</button>
          </div>
          {busy && <p className="muted small mt-4" role="status">Uploading and reading the PDF. Keep this page open until it finishes.</p>}
        </section>
      )}
      {error && <div className="upload-feedback" role="alert"><p className="error">{error}</p><p className="small mt-2">{selectedFile ? "Your selection is still available above. Check it, choose a different file, or confirm again to retry." : "Choose a PDF above to continue."}</p><Link className="small" to="/sponsor/protocols">Check All protocols</Link></div>}
      {uploaded && !busy && (
        <div ref={successRef} className="card mt-4 upload-success" role="status" tabIndex={-1}>
          <p className="strong">{uploaded.already_loaded ? "Protocol already in your workspace" : "Protocol added"}</p>
          <p className="muted small mt-2">{uploaded.name}</p>
          {uploaded.already_loaded && <p className="muted small mt-2">The existing protocol is being used. No duplicate was created.</p>}
          <div className="row row-wrap mt-4">
            {can("protocol.extract") && <Link className="btn btn-teal" to={`/sponsor/p/${uploaded.id}/visits`}>Continue to extraction</Link>}
            <Link className="btn btn-secondary" to="/sponsor/protocols">All protocols</Link>
          </div>
        </div>
      )}
    </div>
  );
}
