import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { EcrfPatientStatus, EcrfProtocolStatus, EcrfStatusOverview } from "../api/types";
import Icon from "../components/Icon";
import NavigationActions from "../components/NavigationActions";
import "../styles/workspace.css";
import "../styles/ecrf-status.css";

function activityLabel(value: string | null) {
  return value ? new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "No hospital updates yet";
}

function latestUpdate(values: (string | null)[]) {
  return values.reduce<string | null>((latest, value) =>
    value && (!latest || Date.parse(value) > Date.parse(latest)) ? value : latest, null);
}

function hasEntries(patient: EcrfPatientStatus) {
  return patient.visits.some((visit) => visit.has_entries);
}

function matchesPatient(patient: EcrfPatientStatus, status: string) {
  if (status === "has_entries") return hasEntries(patient);
  if (status === "no_entries") return patient.visits.length > 0 && !hasEntries(patient);
  if (status === "missing_visits") return patient.visits.some((visit) => !visit.has_entries);
  return true;
}

function matchesStatus(protocol: EcrfProtocolStatus, status: string) {
  return status === "awaiting_patients" ? protocol.patient_count === 0
    : protocol.patients.some((patient) => matchesPatient(patient, status));
}

function protocolStatus(protocol: EcrfProtocolStatus) {
  if (!protocol.locked_version) return { label: "Form unavailable", tone: "no_entries" };
  if (!protocol.patient_count) return { label: "Awaiting patients", tone: "no_entries" };
  return protocol.patients_with_entries
    ? { label: "Hospital entries received", tone: "has_entries" }
    : { label: "No entries yet", tone: "no_entries" };
}

export default function EcrfStatus() {
  const [overview, setOverview] = useState<EcrfStatusOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [params, setParams] = useSearchParams();
  const study = params.get("study") ?? "";
  const protocol = params.get("protocol") ?? "";
  const hospital = params.get("hospital") ?? "";
  const status = params.get("status") ?? "";
  const search = params.get("search") ?? "";
  useEffect(() => {
    const siteId = Number(hospital);
    if (siteId > 0) setExpanded((previous) => new Set([...previous, siteId]));
  }, [hospital]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setOverview(await api.ecrfStatus());
      setRefreshedAt(new Date().toISOString());
      setError(null);
    } catch (failure) {
      setError((failure as Error).message);
      setOverview(null);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const updateFilter = (name: string, value: string) => {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      if (value) next.set(name, value); else next.delete(name);
      if (name === "study") next.delete("protocol");
      return next;
    }, { replace: true });
  };
  const query = search.trim().toLowerCase();
  const hospitals = overview?.hospitals ?? [];
  const groups = hospitals.map((item) => ({
    ...item,
    protocols: item.protocols.filter((form) =>
      (!study || (study === "unassigned" ? form.study_id === null : String(form.study_id) === study)) &&
      (!protocol || String(form.protocol_id) === protocol) && (!hospital || String(item.site_id) === hospital) &&
      (!status || matchesStatus(form, status)) &&
      `${item.site_name} ${item.site_code} ${form.study_name ?? ""} ${form.study_code ?? ""} ${form.protocol_name} ${form.patients.map((patient) => patient.subject_code).join(" ")}`.toLowerCase().includes(query)),
  })).filter((item) => item.protocols.length > 0);
  const forms = groups.flatMap((item) => item.protocols);
  const filtered = Boolean(study || protocol || hospital || status || search);
  const metrics = [
    { label: "Hospitals", value: groups.length, note: "Grouped in one place", icon: "sites" as const },
    { label: "Assigned eCRFs", value: forms.filter((form) => form.assigned && form.locked_version).length, note: "Protocol forms assigned to hospitals", icon: "forms" as const },
    { label: "Patient registrations", value: forms.reduce((total, form) => total + form.patient_count, 0), note: "Hospital registrations per protocol", icon: "patients" as const },
    { label: "Patients with entries", value: forms.reduce((total, form) => total + form.patients_with_entries, 0), note: "At least one saved visit entry", icon: "data" as const },
  ];
  const toggleHospital = (siteId: number) => setExpanded((previous) => {
    const next = new Set(previous);
    if (next.has(siteId)) next.delete(siteId); else next.add(siteId);
    return next;
  });

  return (
    <div className="workspace-dashboard ecrf-status-page">
      <NavigationActions>
        <div className="workspace-tools">
          {refreshedAt && overview && <span className="ecrf-refreshed">Refreshed {new Date(refreshedAt).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}</span>}
          <button className="workspace-refresh" type="button" aria-label="Refresh eCRF status" title="Refresh eCRF status" disabled={loading} onClick={refresh}><Icon name="refresh" className="workspace-icon" /></button>
        </div>
      </NavigationActions>
      <div className="workspace-body" aria-busy={loading}>
        <div className="workspace-heading"><div><p className="study-eyebrow">Updates from your hospitals</p><h1>eCRF Status</h1><p>Follow hospital registrations and visit entries for assigned eCRFs.</p></div></div>
        {error && <div className="workspace-error" role="alert"><strong>Couldn’t load hospital updates.</strong><p>{error}</p><button className="btn btn-secondary btn-sm mt-3" type="button" disabled={loading} onClick={refresh}>Try again</button></div>}
        <div className="ecrf-status-filters" role="group" aria-label="Filter eCRF status">
          <label>Study<select value={study} onChange={(event) => updateFilter("study", event.target.value)}><option value="">All studies</option><option value="unassigned">Unassigned protocols</option>{overview?.studies.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.code}</option>)}</select></label>
          <label>Protocol<select value={protocol} onChange={(event) => updateFilter("protocol", event.target.value)}><option value="">All protocols</option>{overview?.protocols.filter((item) => !study || (study === "unassigned" ? item.study_id === null : String(item.study_id) === study)).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Hospital<select value={hospital} onChange={(event) => updateFilter("hospital", event.target.value)}><option value="">All hospitals</option>{hospitals.map((item) => <option key={item.site_id} value={item.site_id}>{item.site_name}</option>)}</select></label>
          <label>Status<select value={status} onChange={(event) => updateFilter("status", event.target.value)}><option value="">All hospital updates</option><option value="awaiting_patients">Awaiting patient registrations</option><option value="no_entries">Patients with no entries</option><option value="has_entries">Hospital entries received</option><option value="missing_visits">Visits with no entries</option></select></label>
          <label className="ecrf-status-search">Search<input type="search" value={search} placeholder="Hospital, study, protocol or patient code…" onChange={(event) => updateFilter("search", event.target.value)} /></label>
          {filtered && <button className="btn btn-secondary btn-sm" type="button" onClick={() => setParams({})}>Clear filters</button>}
        </div>
        <div className="workspace-metrics">{metrics.map((metric) => <div className="workspace-metric" key={metric.label}><div className="workspace-metric-heading"><span>{metric.label}</span><span className="workspace-metric-icon teal"><Icon name={metric.icon} className="workspace-icon" /></span></div><strong className="workspace-metric-value">{overview ? metric.value.toLocaleString() : "—"}</strong><span className="workspace-metric-note">{metric.note}</span></div>)}</div>
        <section className="ecrf-hospitals" aria-labelledby="ecrf-hospitals-title">
          <div className="ecrf-section-heading"><div><h2 id="ecrf-hospitals-title">Hospital progress</h2><p>Each hospital appears once. Open it to see studies, patients and visit updates.</p></div>{overview && <span>{groups.length} hospital{groups.length === 1 ? "" : "s"}</span>}</div>
          {loading && !overview && !error && <p className="workspace-empty" role="status">Loading hospital updates…</p>}
          {overview && groups.length === 0 && <div className="workspace-study-panel workspace-empty"><h3>{filtered && hospitals.length > 0 ? "No matching hospital updates" : "No hospitals assigned yet"}</h3><p>{filtered && hospitals.length > 0 ? "Try another filter or clear your selection." : "Assigned hospitals will appear here. Their registrations and saved visit entries will update this page."}</p>{hospitals.length === 0 && <Link className="btn btn-secondary btn-sm" to="/sponsor/protocols">View protocols</Link>}</div>}
          {groups.map((item) => {
            const isExpanded = expanded.has(item.site_id);
            const patientCount = item.protocols.reduce((total, form) => total + form.patient_count, 0);
            const lastUpdate = latestUpdate(item.protocols.map((form) => form.last_hospital_update));
            return <article className="ecrf-hospital-card" key={item.site_id} aria-labelledby={`hospital-title-${item.site_id}`}>
              <div className="ecrf-hospital-heading">
                <div className="ecrf-hospital-name"><span className="ecrf-hospital-symbol"><Icon name="sites" className="workspace-icon" /></span><div><h3 id={`hospital-title-${item.site_id}`}>{item.site_name}</h3><p>{item.site_code} · {item.protocols.length} protocol{item.protocols.length === 1 ? "" : "s"}</p></div></div>
                <div className="ecrf-hospital-summary"><div><strong>{patientCount}</strong><span>patient registrations</span></div><div><strong>{activityLabel(lastUpdate)}</strong><span>last hospital update</span></div></div>
                <button className="ecrf-details-toggle" type="button" aria-expanded={isExpanded} aria-controls={`hospital-updates-${item.site_id}`} aria-label={`${isExpanded ? "Hide" : "View"} updates for ${item.site_name}`} onClick={() => toggleHospital(item.site_id)}>{isExpanded ? "Hide updates" : "View updates"}<Icon name="chevron" className="workspace-icon" /></button>
              </div>
              <div className="ecrf-hospital-protocols" id={`hospital-updates-${item.site_id}`} hidden={!isExpanded}>
                {item.protocols.map((form) => {
                  const entryStatus = protocolStatus(form);
                  const searchMatchesForm = `${item.site_name} ${item.site_code} ${form.study_name ?? ""} ${form.study_code ?? ""} ${form.protocol_name}`.toLowerCase().includes(query);
                  const visiblePatients = form.patients.filter((patient) => matchesPatient(patient, status) && (searchMatchesForm || patient.subject_code.toLowerCase().includes(query)));
                  return <section className="ecrf-protocol-panel" key={form.protocol_id} aria-labelledby={`protocol-title-${item.site_id}-${form.protocol_id}`}>
                    <div className="ecrf-protocol-heading"><div><p className="ecrf-study-label">{form.study_name ?? "Unassigned protocol"}{form.study_code ? ` · ${form.study_code}` : ""}</p><h4 id={`protocol-title-${item.site_id}-${form.protocol_id}`}>{form.protocol_name}</h4><p>{form.patient_count} patient registration{form.patient_count === 1 ? "" : "s"} · {form.patients_with_entries} with entries{!form.assigned && " · No longer assigned"}</p>{form.submission.state !== "not_submitted" && <span className={`submission-pill ${form.submission.state}`}>{form.submission.state === "submitted" ? "Hospital submitted for review" : "Changed since submission"}{form.submission.submitted_at && ` · ${activityLabel(form.submission.submitted_at)}`}</span>}</div><span className={`ecrf-entry-status ${entryStatus.tone}`}>{entryStatus.label}</span></div>
                    {visiblePatients.length === 0 ? <p className="ecrf-no-patients">{form.patient_count ? "No patient updates match this filter." : "Waiting for the hospital to register its first patient."}</p> : <div className="workspace-table-wrap"><table className="workspace-table ecrf-patient-table"><caption className="workspace-visually-hidden">Hospital updates for {item.site_name}, {form.protocol_name}</caption><thead><tr><th scope="col">Patient code</th><th scope="col">Latest visit updated</th><th scope="col">Visit updates</th><th scope="col">Last hospital update</th></tr></thead><tbody>{visiblePatients.map((patient) => <tr key={patient.subject_id}>
                      <th scope="row" className="mono">{patient.subject_code}</th>
                      <td>{patient.latest_visits.length ? patient.latest_visits.join(", ") : "No visit entries yet"}</td>
                      <td>{patient.visits.length ? <details className="ecrf-visit-details"><summary>{patient.visits.some((visit) => !visit.has_entries) ? "View visits · some have no entries" : "View saved visit entries"}</summary><ul>{patient.visits.map((visit) => <li key={visit.visit}><div><strong>{visit.visit}</strong><span className={`ecrf-entry-status ${visit.has_entries ? "has_entries" : "no_entries"}`}>{visit.has_entries ? "Entries saved" : "No entries yet"}</span></div>{visit.last_hospital_update && <span className="ecrf-visit-date">{activityLabel(visit.last_hospital_update)}</span>}</li>)}</ul></details> : <span>No visits available on the locked form</span>}</td>
                      <td>{activityLabel(patient.last_hospital_update)}</td>
                    </tr>)}</tbody></table></div>}
                  </section>;
                })}
              </div>
            </article>;
          })}
        </section>
        <p className="ecrf-status-footnote">Hospital-side registrations and saved visit entries only. “Latest visit updated” is not a confirmed current week; visits with no entries are not marked late. Schedule tracking will be added after client confirmation.</p>
      </div>
    </div>
  );
}
