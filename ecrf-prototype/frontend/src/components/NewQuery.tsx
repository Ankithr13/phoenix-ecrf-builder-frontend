import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DataRow } from "../api/types";
import { useAuth } from "../auth/useAuth";

interface Props {
  onDone: () => void;
  onCancel: () => void;
}

interface StudyOpt { id: number; name: string }

/* Write a query from the Queries page: pick the study, the patient, the
   value, say what the question is. A query is always about one entered
   value, which is why the picker ends on a value and not on a free-text
   subject line. Works for both portals: a sponsor sees its protocols and
   every site's patients, a site sees its studies and its own patients. */
export default function NewQuery({ onDone, onCancel }: Props) {
  const { me } = useAuth();
  const isSite = me?.org.type === "site";
  const [studies, setStudies] = useState<StudyOpt[] | null>(null);
  const [study, setStudy] = useState<number | "">("");
  const [rows, setRows] = useState<DataRow[] | null>(null);
  const [subject, setSubject] = useState("");
  const [obs, setObs] = useState<number | "">("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = isSite
      ? api.studies().then((s) => s.map((x) => ({ id: x.id, name: x.name })))
      : api.listProtocols().then((p) => p.filter((x) => x.state === "locked").map((x) => ({ id: x.id, name: x.name })));
    load.then(setStudies).catch((e) => setError((e as Error).message));
  }, [isSite]);

  useEffect(() => {
    setRows(null); setSubject(""); setObs("");
    if (study === "") return;
    api.dataRows(study).then(setRows).catch((e) => setError((e as Error).message));
  }, [study]);

  const subjects = Array.from(new Set((rows ?? []).map((r) => r.subject))).sort();
  const values = (rows ?? []).filter((r) => r.subject === subject && r.status !== "queried");

  const send = async () => {
    if (obs === "" || !text.trim()) return;
    setBusy(true); setError(null);
    try { await api.raiseQuery(obs, text.trim()); onDone(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <div className="card new-query">
      <p className="strong">New query</p>
      <p className="muted small">
        A query is about one entered value. Pick the study, the patient and the value, then say what the question is.
        {isSite ? " The sponsor answers and you close it." : " The site answers, with a corrected value if needed, and you close it."}
      </p>
      <div className="row row-wrap mt-3">
        <label className="ctl">
          Study
          <select className="input" value={study} onChange={(e) => setStudy(e.target.value === "" ? "" : Number(e.target.value))} aria-label="Study">
            <option value="">—</option>
            {(studies ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <label className="ctl">
          Patient
          <select className="input input-mono" value={subject} onChange={(e) => { setSubject(e.target.value); setObs(""); }} disabled={!rows} aria-label="Patient">
            <option value="">—</option>
            {subjects.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
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
      </div>
      {study !== "" && rows && rows.length === 0 && (
        <p className="muted small mt-2">No values have been entered on this study yet, so there is nothing to query.</p>
      )}
      {subject && values.length === 0 && rows && rows.length > 0 && (
        <p className="muted small mt-2">Every value for this patient already has an open query.</p>
      )}
      <div className="row row-wrap mt-3 query-reply">
        <input className="input grow" placeholder="What is the question?" value={text} onChange={(e) => setText(e.target.value)} aria-label="Question" />
        <button type="button" className="btn btn-primary btn-sm" onClick={send} disabled={busy || obs === "" || !text.trim()}>
          {busy ? "Sending…" : "Send query"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
      </div>
      {error && <p className="error small mt-2">{error}</p>}
    </div>
  );
}
