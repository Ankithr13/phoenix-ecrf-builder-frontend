import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { ProtocolListItem, SponsorStudy } from "../api/types";
import { useAuth } from "../auth/useAuth";

const DESTINATIONS = {
  review: { title: "eCRF Management", action: "Review forms", description: "Choose a protocol to review and manage its electronic case report forms." },
  data: { title: "Clinical Data Review", action: "Review data", description: "Choose a protocol to review submitted clinical data." },
  dashboard: { title: "Analytics & Reports", action: "View reports", description: "Choose a protocol to view its analytics and reports." },
};

type Destination = keyof typeof DESTINATIONS;

function ProtocolCard({ protocol, studies, destination, onAssigned }: {
  protocol: ProtocolListItem; studies: SponsorStudy[]; destination?: Destination; onAssigned: () => Promise<void>;
}) {
  const { can } = useAuth();
  const [selectedStudy, setSelectedStudy] = useState(protocol.study_id === null ? "" : String(protocol.study_id));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const section = destination ? DESTINATIONS[destination] : null;
  const changed = selectedStudy !== (protocol.study_id === null ? "" : String(protocol.study_id));

  const assignStudy = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.assignProtocolStudy(protocol.id, selectedStudy ? Number(selectedStudy) : null);
      await onAssigned();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <article className="card protocol-card">
      <div className="row row-between row-top row-wrap">
        <div className="grow">
          <div className="row row-wrap">
            <h2 className="protocol-name">{protocol.name}</h2>
            {protocol.state === "locked" && <span className="pill chip-teal">Locked</span>}
          </div>
          <p className="small muted mt-2">{protocol.pages} pages · ~{protocol.tokens_estimate.toLocaleString()} tokens · Uploaded by {protocol.uploaded_by}</p>
          {protocol.summary && (
            <div className="row row-wrap mt-3">
              <span className="pill chip-teal">{protocol.summary.fields_kept} kept</span>
              <span className="pill chip-rust">{protocol.summary.rejected} rejected</span>
              <span className="pill chip-amber">{protocol.summary.flagged} flagged</span>
              {protocol.summary.est_cost_usd !== undefined && <span className="mono xs muted">{protocol.summary.llm_calls_made} model calls · ${protocol.summary.est_cost_usd.toFixed(4)}</span>}
            </div>
          )}
          <div className="mt-3">
            {protocol.study_id ? (
              <Link className="study-code" to={`/sponsor/studies/${protocol.study_id}`}>{protocol.study_code} · {protocol.study_name}</Link>
            ) : <span className="pill chip-amber">Unassigned</span>}
          </div>
        </div>
        <div className="row row-wrap">
          {protocol.latest_version === null ? (
            can("protocol.extract") && <Link className="btn btn-primary btn-sm" to={`/sponsor/p/${protocol.id}/visits`}>
              {protocol.plan?.visits.length ? "Continue extraction" : "Extract forms"}
            </Link>
          ) : section && destination ? (
            <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${protocol.id}/${destination}`}>{section.action}</Link>
          ) : (
            <>
              <span className="pill">v{protocol.latest_version}</span>
              <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${protocol.id}/review`}>Review</Link>
              <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${protocol.id}/data`}>Data</Link>
              <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${protocol.id}/dashboard`}>Reports</Link>
            </>
          )}
        </div>
      </div>
      {can("study.manage") && (
        <div className="protocol-assignment">
          <label className="label" htmlFor={`protocol-study-${protocol.id}`}>Study assignment</label>
          <div className="row row-wrap">
            <select className="input study-assignment-select" id={`protocol-study-${protocol.id}`} value={selectedStudy} onChange={(event) => setSelectedStudy(event.target.value)} disabled={saving}>
              <option value="">Unassigned</option>
              {studies.map((study) => <option key={study.id} value={study.id}>{study.code} · {study.name}</option>)}
            </select>
            <button className="btn btn-secondary btn-sm" type="button" onClick={assignStudy} disabled={saving || !changed}>{saving ? "Saving…" : "Save assignment"}</button>
          </div>
          {error && <p className="error mt-2" role="alert">{error}</p>}
        </div>
      )}
    </article>
  );
}

export default function Protocols({ destination, studyId }: { destination?: Destination; studyId?: number }) {
  const [params] = useSearchParams();
  const unassignedOnly = studyId === undefined && params.get("unassigned") === "1";
  const pendingOnly = destination === "review" && params.get("pending") === "1";
  const [items, setItems] = useState<ProtocolListItem[]>([]);
  const [studies, setStudies] = useState<SponsorStudy[]>([]);
  const [study, setStudy] = useState<SponsorStudy | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const section = destination ? DESTINATIONS[destination] : null;

  const refresh = useCallback(async () => {
    try {
      const [protocolRows, studyRows, currentStudy] = await Promise.all([
        api.listProtocols({ study_id: studyId, unassigned: unassignedOnly }),
        api.sponsorStudies(),
        studyId === undefined ? Promise.resolve(null) : api.sponsorStudy(studyId),
      ]);
      setItems(protocolRows);
      setStudies(studyRows);
      setStudy(currentStudy);
      setError(null);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setLoading(false);
    }
  }, [studyId, unassignedOnly]);

  useEffect(() => { refresh(); }, [refresh]);

  const visibleItems = pendingOnly ? items.filter((protocol) => protocol.latest_version !== null && protocol.state === "draft") : items;

  return (
    <div className="page">
      <div className="page-head">
        {studyId !== undefined && <Link className="inline small" to="/sponsor/studies">← All studies</Link>}
        {study && <p className="study-eyebrow mt-4">{study.code}</p>}
        <h1 className="page-title">{studyId !== undefined ? study?.name ?? "Study protocols" : pendingOnly ? "Pending eCRF reviews" : section?.title ?? (unassignedOnly ? "Unassigned protocols" : "All protocols")}</h1>
        <p className="muted small">{studyId !== undefined ? "Protocols assigned to this study. Uploads are managed separately from the sidebar." : pendingOnly ? "Draft forms awaiting review or locking." : section?.description ?? "Choose the study each protocol belongs to. Existing forms and clinical data stay with their protocol."}</p>
      </div>
      {error && <p className="error mb-4" role="alert">{error}</p>}
      {studyId === undefined && !destination && (
        <div className="row mb-4">
          <Link className={`btn btn-sm ${unassignedOnly ? "btn-secondary" : "btn-teal"}`} to="/sponsor/protocols">All protocols</Link>
          <Link className={`btn btn-sm ${unassignedOnly ? "btn-teal" : "btn-secondary"}`} to="/sponsor/protocols?unassigned=1">Unassigned</Link>
        </div>
      )}
      {loading && <p className="muted">Loading protocols…</p>}
      {!loading && !error && visibleItems.length === 0 && (
        <div className="empty">
          <h2 className="section-title">{studyId !== undefined ? "No protocols assigned yet" : pendingOnly ? "No pending reviews" : unassignedOnly ? "No unassigned protocols" : "No protocols yet"}</h2>
          <p>{studyId !== undefined ? "Assign an existing protocol here from All protocols. New documents can be added from Upload Protocol in the sidebar." : pendingOnly ? "There are no draft forms awaiting review or locking." : "Use Upload Protocol in the sidebar to add documents to a study."}</p>
          {studyId !== undefined && <Link className="btn btn-secondary mt-3" to="/sponsor/protocols">Manage existing protocols</Link>}
        </div>
      )}
      <div className="stack">
        {visibleItems.map((protocol) => <ProtocolCard key={`${protocol.id}:${protocol.study_id}`} protocol={protocol} studies={studies} destination={destination} onAssigned={refresh} />)}
      </div>
    </div>
  );
}
