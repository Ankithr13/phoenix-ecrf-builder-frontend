import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DataRow, NewQuery as NewQueryBody, SiteRow, SubjectRow } from "../api/types";
import { useAuth } from "../auth/useAuth";

interface Props {
  onDone: () => void;
  onCancel: () => void;
}

interface StudyOpt { id: number; name: string; visits: string[] }
type About = "study" | "patient" | "visit" | "value";

const ABOUT: { key: About; label: string; hint: string }[] = [
  { key: "study", label: "The study", hint: "The form, a procedure, the schedule, enrolment: anything not tied to one patient." },
  { key: "patient", label: "A patient", hint: "Something about one patient across visits: consent, eligibility, a missed visit." },
  { key: "visit", label: "A visit", hint: "One patient's visit: timing, what was or was not done." },
  { key: "value", label: "A value", hint: "One entered reading. The site can answer with a corrected value." },
];

/* Write a query from the Queries page, for either portal. Pick what it is
   about, from the whole study down to one value; the picker asks only for
   what that level needs. A sponsor asking about the study as a whole
   names the site it is asking. */
export default function NewQuery({ onDone, onCancel }: Props) {
  const { me } = useAuth();
  const isSite = me?.org.type === "site";
  const [studies, setStudies] = useState<StudyOpt[] | null>(null);
  const [study, setStudy] = useState<number | "">("");
  const [about, setAbout] = useState<About>("study");
  const [sites, setSites] = useState<SiteRow[]>([]);
  const [site, setSite] = useState<number | "">("");
  const [subjects, setSubjects] = useState<SubjectRow[]>([]);
  const [subject, setSubject] = useState("");
  const [visit, setVisit] = useState("");
  const [rows, setRows] = useState<DataRow[]>([]);
  const [obs, setObs] = useState<number | "">("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Studies: a site's assigned studies, or a sponsor's locked protocols.
  useEffect(() => {
    const load = isSite
      ? api.studies().then((s) => s.map((x) => ({ id: x.id, name: x.name, visits: x.visits })))
      : api.listProtocols().then(async (p) => {
          const locked = p.filter((x) => x.state === "locked");
          return Promise.all(locked.map(async (x) => {
            const d = await api.draft(x.id);
            return { id: x.id, name: x.name, visits: d.draft?.forms.map((f) => f.visit) ?? [] };
          }));
        });
    load.then(setStudies).catch((e) => setError((e as Error).message));
  }, [isSite]);

  // Everything below the study resets when it changes.
  useEffect(() => {
    setSite(""); setSubject(""); setVisit(""); setObs(""); setSubjects([]); setRows([]); setSites([]);
    if (study === "") return;
    api.subjects(study).then(setSubjects).catch(() => setSubjects([]));
    api.dataRows(study).then(setRows).catch(() => setRows([]));
    if (!isSite) api.sites(study).then((s) => setSites(s.filter((x) => x.assigned))).catch(() => setSites([]));
  }, [study, isSite]);

  const current = studies?.find((s) => s.id === study) ?? null;
  const values = rows.filter((r) => r.subject === subject && (!visit || r.visit === visit) && r.status !== "queried");
  const needSite = !isSite && about === "study";
  const needSubject = about !== "study";
  const needVisit = about === "visit";
  const needValue = about === "value";
  const ready = study !== "" && text.trim() !== ""
    && (!needSite || site !== "")
    && (!needSubject || subject !== "")
    && (!needVisit || visit !== "")
    && (!needValue || obs !== "");

  const send = async () => {
    if (!ready || typeof study !== "number") return;
    const body: NewQueryBody = { protocol_id: study, text: text.trim() };
    if (needSite && site !== "") body.site_org_id = site;
    if (needSubject) body.subject_code = subject;
    if (needVisit) body.visit = visit;
    if (needValue && obs !== "") body.observation_id = obs;
    setBusy(true); setError(null);
    try { await api.newQuery(body); onDone(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <div className="card new-query">
      <p className="strong">New query</p>
      <p className="muted small">
        {isSite ? "Ask the sponsor. They answer; you close it once the answer settles it." : "Ask a site. They answer; you close it once the answer settles it."}
      </p>

      <div className="row row-wrap mt-3">
        <label className="ctl">
          Study
          <select className="input" value={study} onChange={(e) => setStudy(e.target.value === "" ? "" : Number(e.target.value))} aria-label="Study">
            <option value="">—</option>
            {(studies ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <div className="ctl">
          About
          <div className="row row-wrap">
            {ABOUT.map((a) => (
              <button key={a.key} type="button" className={`chip-btn${about === a.key ? " active" : ""}`} title={a.hint}
                      onClick={() => { setAbout(a.key); setObs(""); if (a.key === "study") { setSubject(""); setVisit(""); } if (a.key === "patient") setVisit(""); }}>
                {a.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <p className="muted small mt-1">{ABOUT.find((a) => a.key === about)?.hint}</p>

      <div className="row row-wrap mt-2">
        {needSite && (
          <label className="ctl">
            Site to ask
            <select className="input" value={site} onChange={(e) => setSite(e.target.value === "" ? "" : Number(e.target.value))} disabled={study === ""} aria-label="Site">
              <option value="">—</option>
              {sites.map((s) => <option key={s.org_id} value={s.org_id}>{s.code} · {s.name}</option>)}
            </select>
          </label>
        )}
        {needSubject && (
          <label className="ctl">
            Patient
            <select className="input input-mono" value={subject} onChange={(e) => { setSubject(e.target.value); setObs(""); }} disabled={study === ""} aria-label="Patient">
              <option value="">—</option>
              {subjects.map((s) => <option key={s.id} value={s.code}>{s.code}{!isSite && s.site ? ` (${s.site})` : ""}</option>)}
            </select>
          </label>
        )}
        {needVisit && (
          <label className="ctl">
            Visit
            <select className="input" value={visit} onChange={(e) => { setVisit(e.target.value); setObs(""); }} disabled={!current} aria-label="Visit">
              <option value="">—</option>
              {(current?.visits ?? []).map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
        )}
        {needValue && (
          <label className="ctl ctl-wide">
            Value
            <select className="input" value={obs} onChange={(e) => setObs(e.target.value === "" ? "" : Number(e.target.value))} disabled={!subject} aria-label="Value">
              <option value="">—</option>
              {values.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.visit} · {r.field}{r.repeat > 1 ? ` · ${r.repeat}` : ""} = {r.value ?? "—"} ({r.status})
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {needValue && subject && values.length === 0 && (
        <p className="muted small mt-2">No values on file for this patient{visit ? " at this visit" : ""} that are not already under query. Ask about the patient or the visit instead.</p>
      )}
      {needSubject && study !== "" && subjects.length === 0 && (
        <p className="muted small mt-2">No patients registered on this study yet.</p>
      )}

      <div className="row row-wrap mt-3 query-reply">
        <input className="input grow" placeholder="What is the question?" value={text} onChange={(e) => setText(e.target.value)} aria-label="Question" />
        <button type="button" className="btn btn-primary btn-sm" onClick={send} disabled={busy || !ready}>{busy ? "Sending…" : "Send query"}</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
      </div>
      {error && <p className="error small mt-2">{error}</p>}
    </div>
  );
}
