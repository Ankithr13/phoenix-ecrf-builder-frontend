import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ProtocolListItem } from "../api/types";
import { useAuth } from "../auth/useAuth";

const DESTINATIONS = {
  review: { title: "eCRF Management", action: "Review forms", description: "Choose a protocol to review and manage its electronic case report forms." },
  data: { title: "Clinical Data Review", action: "Review data", description: "Choose a protocol to review submitted clinical data." },
  dashboard: { title: "Analytics & Reports", action: "View reports", description: "Choose a protocol to view its analytics and reports." },
};

export default function Protocols({ destination, uploadOnly = false }: { destination?: keyof typeof DESTINATIONS; uploadOnly?: boolean }) {
  const { can } = useAuth();
  const [items, setItems] = useState<ProtocolListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);       // "sample" | "upload"
  const [error, setError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<{ id: number; name: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const section = destination ? DESTINATIONS[destination] : null;

  const refresh = useCallback(async () => {
    try {
      setItems(await api.listProtocols());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const loadSample = async () => {
    setBusy("sample"); setError(null); setUploaded(null);
    try { setUploaded(await api.loadSample()); await refresh(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  };

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setBusy("upload"); setError(null); setUploaded(null);
    try { setUploaded(await api.upload(f)); await refresh(); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(null); if (fileRef.current) fileRef.current.value = ""; }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">{uploadOnly ? "Upload Protocol" : section?.title ?? "Protocols"}</h1>
        {section && <p className="muted small">{section.description}</p>}
        {uploadOnly && <p className="muted small">Upload a protocol PDF or load the sample, then open Protocols under Studies to continue.</p>}
      </div>

      {!destination && (
      <div className="card">
        <div className="row row-top">
          {can("protocol.upload") && (
            <>
              <button type="button" className="btn btn-primary" onClick={loadSample} disabled={busy !== null}>
                {busy === "sample" ? "Loading…" : "Load sample protocol"}
              </button>
              <label className="drop">
                <input ref={fileRef} type="file" accept="application/pdf,.pdf" onChange={upload} disabled={busy !== null} />
                {busy === "upload" ? "Uploading…" : "Upload a protocol PDF"}
              </label>
            </>
          )}
        </div>
      </div>
      )}
      {error && <p className="error mt-3">{error}</p>}

      {uploadOnly && uploaded && !busy && !error && (
        <div className="card mt-4" role="status">
          <p className="strong">{uploaded.name} is ready</p>
          <p className="muted small mt-2">The protocol has been added to your workspace.</p>
          {can("protocol.extract") && <Link className="btn btn-secondary mt-3" to={`/sponsor/p/${uploaded.id}/visits`}>Continue to extraction</Link>}
        </div>
      )}

      {uploadOnly && !error && !busy && (
        <p className="small mt-4"><Link className="inline" to="/sponsor">View protocols</Link></p>
      )}

      {!uploadOnly && (
      <div className="mt-5 stack">
        {loading && <p className="muted">Loading…</p>}
        {!loading && items.length === 0 && (
          <div className="empty">
            <p>No protocols yet. Load the sample or upload a PDF to get started.</p>
            {destination && can("protocol.upload") && <Link className="btn btn-secondary mt-3" to="/sponsor/upload">Upload Protocol</Link>}
          </div>
        )}
        {items.map((p) => (
          <div className="card card-hover" key={p.id} style={{ marginTop: 0 }}>
            <div className="row row-between row-top">
              <div className="grow">
                <div className="row">
                  <span className="strong">{p.name}</span>
                  {p.state === "locked" && <span className="pill chip-teal">locked</span>}
                </div>
                <div className="mono small muted mt-2">
                  {p.pages} pages · ~{p.tokens_estimate.toLocaleString()} tokens · by {p.uploaded_by}
                </div>
              </div>
              {p.latest_version === null ? (
                can("protocol.extract") && <Link className="btn btn-primary" to={`/sponsor/p/${p.id}/visits`}>
                  {p.plan && p.plan.visits.length ? "Continue extraction" : "Extract"}
                </Link>
              ) : (
                section && destination ? (
                  <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${p.id}/${destination}`}>{section.action}</Link>
                ) : <div className="row row-wrap">
                  {p.summary && p.summary.est_cost_usd !== undefined && (
                    <span className="mono xs muted">
                      {p.summary.llm_calls_made} call{p.summary.llm_calls_made === 1 ? "" : "s"}
                      {p.summary.llm_calls_from_cache ? ` + ${p.summary.llm_calls_from_cache} from cache` : ""} · ${p.summary.est_cost_usd.toFixed(4)}
                    </span>
                  )}
                  {p.summary && (
                    <>
                      <span className="pill chip-teal">{p.summary.fields_kept} kept</span>
                      <span className="pill chip-rust">{p.summary.rejected} rejected</span>
                      <span className="pill chip-amber">{p.summary.flagged} flagged</span>
                    </>
                  )}
                  <span className="pill">v{p.latest_version}</span>
                  <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${p.id}/review`}>Review</Link>
                  <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${p.id}/data`}>Data</Link>
                  <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${p.id}/dashboard`}>Dashboard</Link>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
      )}
    </div>
  );
}
