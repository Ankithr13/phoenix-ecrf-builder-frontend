import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { ProtocolListItem, SponsorStudy } from "../api/types";
import { useAuth } from "../auth/useAuth";
import "../styles/review-workflow.css";

type ReviewStage = "all" | "not_extracted" | "needs_review" | "locked";
const STAGES: { value: ReviewStage; label: string }[] = [
  { value: "all", label: "All" }, { value: "not_extracted", label: "Not extracted" },
  { value: "needs_review", label: "Needs review / finalization" }, { value: "locked", label: "Locked" },
];

function reviewStage(protocol: ProtocolListItem): ReviewStage {
  return protocol.latest_version === null ? "not_extracted" : protocol.state === "locked" ? "locked" : "needs_review";
}

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
  const remaining = protocol.review_blockers ? protocol.review_blockers.draft + protocol.review_blockers.flagged : null;
  const reviewLabel = protocol.state === "locked" ? "View locked form" : remaining === 0 ? "Review & finalize" : "Continue review";

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
            {protocol.latest_version === null ? <span className="pill">Not extracted</span> : <>
              <span className="pill">v{protocol.latest_version}</span>
              {protocol.state !== "locked" && <span className="pill chip-amber">{remaining === 0 ? "Draft — ready to finalize" : "Draft — review incomplete"}</span>}
            </>}
          </div>
          <p className="small muted mt-2">{protocol.pages} pages · ~{protocol.tokens_estimate.toLocaleString()} tokens · Uploaded by {protocol.uploaded_by}</p>
          {destination === "review" && protocol.state !== "locked" && remaining !== null && <p className="small muted mt-2">{remaining} field{remaining === 1 ? " still needs" : "s still need"} a decision across all visits.</p>}
          {protocol.summary && destination !== "review" && (
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
            <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${protocol.id}/${destination}`}>{destination === "review" ? reviewLabel : section.action}</Link>
          ) : (
            <>
              <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${protocol.id}/review`}>{reviewLabel}</Link>
              <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${protocol.id}/data`}>Data</Link>
              <Link className="btn btn-secondary btn-sm" to={`/sponsor/p/${protocol.id}/dashboard`}>Reports</Link>
            </>
          )}
        </div>
      </div>
      {can("study.manage") && destination !== "review" && (
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
  const [params, setParams] = useSearchParams();
  const unassignedOnly = studyId === undefined && params.get("unassigned") === "1";
  const pendingOnly = destination === "review" && params.get("pending") === "1";
  const requestedStage = params.get("stage");
  const stage = pendingOnly ? "needs_review" : STAGES.find((item) => item.value === requestedStage)?.value ?? "all";
  const search = params.get("search") ?? "";
  const studyFilter = params.get("study") ?? "";
  const setFilter = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (pendingOnly) next.set("stage", "needs_review");
    next.delete("pending");
    if (value) next.set(name, value); else next.delete(name);
    setParams(next, { replace: true });
  };
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

  const visibleItems = destination === "review" ? items.filter((protocol) =>
    (stage === "all" || reviewStage(protocol) === stage) &&
    (!studyFilter || (studyFilter === "unassigned" ? protocol.study_id === null : String(protocol.study_id) === studyFilter)) &&
    `${protocol.name} ${protocol.study_code ?? ""} ${protocol.study_name ?? ""}`.toLowerCase().includes(search.trim().toLowerCase())) : items;
  const groupedItems = new Map<number | null, { label: string; protocols: ProtocolListItem[] }>();
  for (const protocol of visibleItems) {
    const group = groupedItems.get(protocol.study_id) ?? { label: protocol.study_id ? `${protocol.study_code} · ${protocol.study_name}` : "Unassigned protocols", protocols: [] };
    group.protocols.push(protocol);
    groupedItems.set(protocol.study_id, group);
  }

  return (
    <div className="page">
      <div className="page-head">
        {studyId !== undefined && <Link className="inline small" to="/sponsor/studies">← All studies</Link>}
        {study && <p className="study-eyebrow mt-4">{study.code}</p>}
        <h1 className="page-title">{studyId !== undefined ? study?.name ?? "Study protocols" : pendingOnly ? "Pending eCRF reviews" : section?.title ?? (unassignedOnly ? "Unassigned protocols" : "All protocols")}</h1>
        <p className="muted small">{studyId !== undefined ? "Protocols assigned to this study. Uploads are managed separately from the sidebar." : pendingOnly ? "Draft forms awaiting review or locking." : section?.description ?? "Choose the study each protocol belongs to. Existing forms and clinical data stay with their protocol."}</p>
      </div>
      {destination === "review" && <div className="review-management-filters">
        <div className="review-management-stages" role="group" aria-label="Form stage">
          {STAGES.map((item) => <button key={item.value} type="button" className={`btn btn-sm ${stage === item.value ? "btn-teal" : "btn-secondary"}`} aria-pressed={stage === item.value} onClick={() => setFilter("stage", item.value)}>{item.label} ({items.filter((protocol) => item.value === "all" || reviewStage(protocol) === item.value).length})</button>)}
        </div>
        <input className="input" type="search" aria-label="Search forms by protocol or study" placeholder="Search by protocol, study name or ID" value={search} onChange={(event) => setFilter("search", event.target.value)} />
        <select className="input" aria-label="Filter forms by study" value={studyFilter} onChange={(event) => setFilter("study", event.target.value)}>
          <option value="">All studies</option><option value="unassigned">Unassigned protocols</option>
          {studies.map((option) => <option key={option.id} value={option.id}>{option.code} · {option.name}</option>)}
        </select>
        <p className="small muted">Drafts remain here until finalized and locked. Open the same review from a study or from this list.</p>
      </div>}
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
          <h2 className="section-title">{destination === "review" && items.length > 0 ? "No forms match these filters" : studyId !== undefined ? "No protocols assigned yet" : pendingOnly ? "No pending reviews" : unassignedOnly ? "No unassigned protocols" : "No protocols yet"}</h2>
          <p>{destination === "review" && items.length > 0 ? "Try another stage, study or search." : studyId !== undefined ? "Assign an existing protocol here from All protocols. New documents can be added from Upload Protocol in the sidebar." : pendingOnly ? "There are no draft forms awaiting review or locking." : "Use Upload Protocol in the sidebar to add documents to a study."}</p>
          {studyId !== undefined && <Link className="btn btn-secondary mt-3" to="/sponsor/protocols">Manage existing protocols</Link>}
        </div>
      )}
      {destination === "review" ? [...groupedItems.entries()].map(([groupId, group]) => <section className="review-study-group" key={groupId ?? "unassigned"} aria-label={group.label}>
        <h2>{groupId ? <Link to={`/sponsor/studies/${groupId}`}>{group.label}</Link> : group.label}</h2>
        <div className="stack">{group.protocols.map((protocol) => <ProtocolCard key={`${protocol.id}:${protocol.study_id}`} protocol={protocol} studies={studies} destination={destination} onAssigned={refresh} />)}</div>
      </section>) : <div className="stack">
        {visibleItems.map((protocol) => <ProtocolCard key={`${protocol.id}:${protocol.study_id}`} protocol={protocol} studies={studies} destination={destination} onAssigned={refresh} />)}
      </div>}
    </div>
  );
}
