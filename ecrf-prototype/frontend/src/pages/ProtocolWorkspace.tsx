import { Link, Navigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { useProtocols } from "../hooks/useProtocols";
import { matchesProtocol, nextProtocolAction, protocolFilter } from "../workspace/protocolPresentation";
import "../styles/review-workflow.css";

type Destination = "review" | "data" | "dashboard";
const SECTIONS = { review: { title: "eCRF Management", action: "Continue review", permission: "protocol.view" }, data: { title: "Clinical Data Review", action: "Review submitted answers", permission: "listing.view" }, dashboard: { title: "Analytics & Reports", action: "View reports", permission: "dashboard.view" } };
const STAGES = [{ value: "all", label: "All" }, { value: "not_extracted", label: "Not extracted" }, { value: "draft", label: "Needs review / finalization" }, { value: "locked", label: "Locked" }];

export default function ProtocolWorkspace({ destination }: { destination?: Destination }) {
  const { can } = useAuth();
  const { rows, loading, error, refresh } = useProtocols();
  const [params, setParams] = useSearchParams();
  const section = destination ? SECTIONS[destination] : null;
  const search = params.get("search") ?? "";
  const stage = params.get("pending") === "1" ? "draft" : protocolFilter(params.get("stage"));
  const filter = (name: string, value: string) => { const next = new URLSearchParams(params); next.delete("pending"); if (value) next.set(name, value); else next.delete(name); setParams(next, { replace: true }); };
  if (section && !can(section.permission)) return <Navigate to="/" replace />;
  const shown = rows.filter((protocol) => matchesProtocol(protocol, stage, search));
  return <div className="page">
    <div className="page-head"><h1 className="page-title">{section?.title ?? "All protocols"}</h1><p className="muted small">{destination === "data" ? "Choose a protocol to verify submitted hospital answers. Hospital drafts remain private under the existing submission rules." : destination === "dashboard" ? "Choose a protocol to open its queries, page status and analysis results." : "Choose a protocol to continue. Review links open the same saved form from every entry point."}</p></div>
    <div className="review-management-filters"><div className="review-management-stages" role="group" aria-label="Protocol stage">{STAGES.map((item) => <button key={item.value} type="button" className={`btn btn-sm ${stage === item.value ? "btn-teal" : "btn-secondary"}`} aria-pressed={stage === item.value} onClick={() => filter("stage", item.value)}>{item.label}</button>)}</div><input className="input" type="search" aria-label="Search protocols" placeholder="Search by protocol name or filename" value={search} onChange={(event) => filter("search", event.target.value)} /><button className="btn btn-secondary" type="button" onClick={refresh} disabled={loading}>Refresh</button></div>
    {loading && <p className="muted" role="status">Loading protocols…</p>}{error && <p className="error" role="alert">{error}</p>}
    {!loading && !error && shown.length === 0 && <div className="empty"><h2 className="section-title">{rows.length ? "No matching protocols" : "No protocols yet"}</h2><p>Try another search or stage.{can("protocol.upload") && <> New files can be added from <Link to="/sponsor/upload">Upload Protocol</Link>.</>}</p></div>}
    <div className="stack">{shown.map((protocol) => <article className="card" key={protocol.id}><div className="row row-wrap row-between"><div className="grow"><h2 className="protocol-name">{protocol.name}</h2><div className="row row-wrap mt-2"><span className={`pill ${protocol.state === "locked" ? "chip-teal" : protocol.state === "draft" ? "chip-amber" : ""}`}>{protocol.latest_version === null ? "Not extracted" : protocol.state === "locked" ? "Locked template" : "Draft — review / finalization pending"}</span>{protocol.latest_version !== null && <span className="pill">v{protocol.latest_version}</span>}</div><p className="muted small mt-2">{protocol.pages} pages · Uploaded by {protocol.uploaded_by}</p></div><div className="row row-wrap">
      {protocol.latest_version === null ? can("protocol.extract") ? <Link className="btn btn-teal" to={`/sponsor/p/${protocol.id}/visits`}>{protocol.plan?.visits.length ? "Continue extraction" : "Extract forms"}</Link> : <Link className="btn btn-secondary" to={`/sponsor/p/${protocol.id}/review`}>View protocol</Link> : <>
        <Link className="btn btn-teal" to={`/sponsor/p/${protocol.id}/${destination ?? "review"}`}>{destination && destination !== "review" ? section?.action : nextProtocolAction(protocol, can).label}</Link>
        {!destination && can("listing.view") && <Link className="btn btn-secondary" to={`/sponsor/p/${protocol.id}/data`}>Review data</Link>}
        {!destination && can("dashboard.view") && <Link className="btn btn-secondary" to={`/sponsor/p/${protocol.id}/dashboard`}>Reports</Link>}
      </>}
    </div></div></article>)}</div>
  </div>;
}
