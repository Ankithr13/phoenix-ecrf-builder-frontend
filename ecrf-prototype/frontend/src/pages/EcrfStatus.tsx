import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { PageStatus, ProtocolListItem } from "../api/types";
import { useAuth } from "../auth/useAuth";
import { useProtocols } from "../hooks/useProtocols";
import Icon from "../components/Icon";
import NavigationActions from "../components/NavigationActions";
import "../styles/workspace.css";
import "../styles/ecrf-status.css";

type Site = PageStatus["sites"][number];
type HospitalProtocol = { protocol: ProtocolListItem; site: Site };
const STATES = [{ value: "", label: "Any visit status" }, { value: "not_started", label: "Not started" }, { value: "draft", label: "Draft entries" }, { value: "submitted", label: "Submitted visits" }, { value: "monitor_reviewed", label: "Monitor reviewed" }, { value: "approved", label: "Approved" }, { value: "signed", label: "Signed" }] as const;

export default function EcrfStatus({ previewOnly = false }: { previewOnly?: boolean }) {
  const { me, can } = useAuth();
  const allowed = !previewOnly && can("dashboard.subject_level");
  const { rows: protocols, loading, error, refresh } = useProtocols(allowed);
  const [params, setParams] = useSearchParams();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const search = params.get("search") ?? "";
  const protocolFilter = params.get("protocol") ?? "";
  const hospitalFilter = params.get("hospital") ?? "";
  const status = STATES.find((item) => item.value === params.get("status"))?.value ?? "";
  const updateFilter = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value); else next.delete(name);
    setParams(next, { replace: true });
  };
  const key = JSON.stringify([me?.user.id, protocols.map((protocol) => [protocol.id, protocol.latest_version, protocol.state])]);
  const [result, setResult] = useState<{ key: string; rows: HospitalProtocol[]; failures: string[] } | null>(null);
  useEffect(() => {
    if (!allowed || loading || error) return;
    let active = true;
    Promise.all(protocols.filter((protocol) => protocol.state === "locked").map(async (protocol) => {
      try { const response = await api.pageStatus(protocol.id); return { rows: response.sites.map((site) => ({ protocol, site })), failure: null }; }
      catch { return { rows: [], failure: protocol.name }; }
    })).then((responses) => { if (active) setResult({ key, rows: responses.flatMap((response) => response.rows), failures: responses.flatMap((response) => response.failure ? [response.failure] : []) }); });
    return () => { active = false; };
  }, [allowed, key, protocols, loading, error]);
  const current = !allowed ? { key, rows: [], failures: [] } : !loading && !error && result?.key === key ? result : null;
  const hospitals = new Map<string, { name: string; rows: HospitalProtocol[] }>();
  const hospitalOptions = new Map((current?.rows ?? []).map((row) => [row.site.site, row.site.site_name]));
  const query = search.trim().toLowerCase();
  for (const row of current?.rows ?? []) {
    if (protocolFilter && String(row.protocol.id) !== protocolFilter || hospitalFilter && row.site.site !== hospitalFilter) continue;
    const subjects = row.site.subjects.filter((subject) => (!status || subject[status] > 0) && `${row.site.site} ${row.site.site_name} ${row.protocol.name} ${subject.code}`.toLowerCase().includes(query));
    if (!subjects.length && (search || status || row.site.subjects.length)) continue;
    const group = hospitals.get(row.site.site) ?? { name: row.site.site_name, rows: [] };
    group.rows.push({ ...row, site: { ...row.site, subjects } }); hospitals.set(row.site.site, group);
  }
  const groups = [...hospitals];
  const forms = groups.flatMap(([, group]) => group.rows);
  const metrics = [
    { label: "Hospitals", value: groups.length, note: "Grouped in one place", icon: "sites" as const },
    { label: "Hospital eCRFs", value: forms.length, note: "Locked forms with hospital progress", icon: "forms" as const },
    { label: "Patient registrations", value: forms.reduce((total, row) => total + row.site.subjects.length, 0), note: "Hospital registrations per protocol", icon: "patients" as const },
    { label: "Patients with submitted visits", value: forms.reduce((total, row) => total + row.site.subjects.filter((subject) => subject.submitted > 0).length, 0), note: "Registrations with submitted visits", icon: "data" as const },
  ];
  const toggleHospital = (code: string) => setExpanded((previous) => { const next = new Set(previous); if (next.has(code)) next.delete(code); else next.add(code); return next; });
  const filtered = Boolean(search || status || protocolFilter || hospitalFilter);
  return <div className="workspace-dashboard ecrf-status-page">
    <NavigationActions><div className="workspace-tools"><button className="workspace-refresh" type="button" aria-label="Refresh eCRF status" title="Refresh eCRF status" disabled={loading || !allowed} onClick={refresh}><Icon name="refresh" className="workspace-icon" /></button></div></NavigationActions>
    <div className="workspace-body" aria-busy={loading || (!error && !current)}>
      <div className="workspace-heading"><div><p className="study-eyebrow">Updates from your hospitals</p><h1>eCRF Status</h1><p>Follow hospital registrations and visit submissions for assigned eCRFs.</p></div></div>
      {!allowed && <div className="feature-preview-notice" role="note"><span className="pill chip-amber">Layout preview</span><p>Your current role cannot access live hospital progress. No protected records are loaded. Empty placeholders preserve this section’s layout.</p></div>}
      {error && <div className="workspace-error" role="alert"><strong>Couldn’t load hospital updates.</strong><p>{error}</p><button className="btn btn-secondary btn-sm mt-3" type="button" onClick={refresh} disabled={loading}>Try again</button></div>}
      {current && current.failures.length > 0 && <div className="workspace-error" role="alert">Some progress could not be loaded: {current.failures.join(", ")}. Results below are partial. Use Refresh to retry.</div>}
      <div className="ecrf-status-filters" role="group" aria-label="Filter eCRF status">
        <label>Study<select disabled aria-label="Filter progress by study"><option>Study grouping not connected</option></select></label>
        <label>Protocol<select disabled={!allowed} value={protocolFilter} onChange={(event) => updateFilter("protocol", event.target.value)} aria-label="Filter progress by protocol"><option value="">All protocols</option>{protocols.map((protocol) => <option key={protocol.id} value={protocol.id}>{protocol.name}</option>)}</select></label>
        <label>Hospital<select disabled={!allowed} value={hospitalFilter} onChange={(event) => updateFilter("hospital", event.target.value)} aria-label="Filter progress by hospital"><option value="">All hospitals</option>{[...hospitalOptions].map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select></label>
        <label>Status<select disabled={!allowed} value={status} onChange={(event) => updateFilter("status", event.target.value)} aria-label="Filter progress by status">{STATES.map((stage) => <option key={stage.value} value={stage.value}>{stage.label}</option>)}</select></label>
        <label className="ecrf-status-search">Search<input type="search" disabled={!allowed} value={search} aria-label="Search hospital progress" placeholder="Hospital, protocol or patient code…" onChange={(event) => updateFilter("search", event.target.value)} /></label>
        {filtered && <button className="btn btn-secondary btn-sm" type="button" onClick={() => setParams({})}>Clear filters</button>}
      </div>
      <div className="workspace-metrics">{metrics.map((metric) => <div className="workspace-metric" key={metric.label}><div className="workspace-metric-heading"><span>{metric.label}</span><span className="workspace-metric-icon teal"><Icon name={metric.icon} className="workspace-icon" /></span></div><strong className="workspace-metric-value">{allowed && current ? metric.value.toLocaleString() : "—"}</strong><span className="workspace-metric-note">{metric.note}</span></div>)}</div>
      <section className="ecrf-hospitals" aria-labelledby="ecrf-hospitals-title">
        <div className="ecrf-section-heading"><div><h2 id="ecrf-hospitals-title">Hospital progress</h2><p>Each hospital appears once. Open it to see protocols, patients and visit updates.</p></div>{allowed && current && <span>{groups.length} hospital{groups.length === 1 ? "" : "s"}</span>}</div>
        {loading || (!error && !current) ? <p className="workspace-empty" role="status">Loading hospital updates…</p> : null}
        {current && !groups.length && <div className="workspace-study-panel workspace-empty"><h3>{!allowed ? "Hospital progress preview" : filtered ? "No matching hospital updates" : "No hospital progress yet"}</h3><p>{!allowed ? "Empty placeholders only. Live hospital records are unavailable for your current role." : filtered ? "Try another filter or clear your selection." : "Hospital registrations and visit updates will appear here as progress becomes available."}</p><Link className="btn btn-secondary btn-sm" to="/sponsor/protocols">View protocols</Link></div>}
        {groups.map(([code, group]) => {
          const isExpanded = expanded.has(code);
          return <article className="ecrf-hospital-card" key={code} aria-labelledby={`hospital-title-${code}`}>
            <div className="ecrf-hospital-heading">
              <div className="ecrf-hospital-name"><span className="ecrf-hospital-symbol"><Icon name="sites" className="workspace-icon" /></span><div><h3 id={`hospital-title-${code}`}>{group.name}</h3><p>{code} · {group.rows.length} protocol{group.rows.length === 1 ? "" : "s"}</p></div></div>
              <div className="ecrf-hospital-summary"><div><strong>{group.rows.reduce((total, row) => total + row.site.subjects.length, 0)}</strong><span>patient registrations</span></div><div><strong>—</strong><span>last hospital update · not connected</span></div></div>
              <button className="ecrf-details-toggle" type="button" aria-expanded={isExpanded} aria-controls={`hospital-updates-${code}`} aria-label={`${isExpanded ? "Hide" : "View"} updates for ${group.name}`} onClick={() => toggleHospital(code)}>{isExpanded ? "Hide updates" : "View updates"}<Icon name="chevron" className="workspace-icon" /></button>
            </div>
            <div className="ecrf-hospital-protocols" id={`hospital-updates-${code}`} hidden={!isExpanded}>
              {group.rows.map(({ protocol, site }) => <section className="ecrf-protocol-panel" key={protocol.id}>
                <div className="ecrf-protocol-heading"><div><p className="ecrf-study-label">Study grouping not connected</p><h4>{protocol.name}</h4><p>{site.subjects.length} patient registration{site.subjects.length === 1 ? "" : "s"}</p></div><span className="ecrf-entry-status has_entries">Visit progress available</span></div>
                {!site.subjects.length ? <p className="ecrf-no-patients">Waiting for hospital patient registrations.</p> : <div className="workspace-table-wrap"><table className="workspace-table ecrf-patient-table"><caption className="workspace-visually-hidden">Hospital updates for {group.name}, {protocol.name}</caption><thead><tr><th scope="col">Patient code</th><th scope="col">Latest visit updated</th><th scope="col">Visit updates</th><th scope="col">Last hospital update</th><th scope="col">Action</th></tr></thead><tbody>{site.subjects.map((subject) => <tr key={subject.id}>
                  <th scope="row" className="mono">{subject.code}</th><td>—</td>
                  <td><details className="ecrf-visit-details"><summary>View visit status</summary><ul>{STATES.filter((stage) => stage.value).map((stage) => <li key={stage.value}><div><strong>{stage.label}</strong><span>{subject[stage.value as Exclude<typeof stage.value, "">]}</span></div></li>)}</ul></details></td>
                  <td>—</td><td>{can("listing.view") ? <Link to={`/sponsor/p/${protocol.id}/data?subject=${encodeURIComponent(subject.code)}`}>Review submitted answers</Link> : <Link to={`/sponsor/p/${protocol.id}/dashboard`}>View report</Link>}</td>
                </tr>)}</tbody></table></div>}
              </section>)}
            </div>
          </article>;
        })}
      </section>
      <p className="ecrf-status-footnote">Visit submissions remain patient-based. Signed visits also count as approved. Visit names and last-update times are not available yet; no current week, schedule or late status is inferred.</p>
    </div>
  </div>;
}
