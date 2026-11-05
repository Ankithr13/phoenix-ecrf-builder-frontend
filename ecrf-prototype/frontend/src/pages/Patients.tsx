import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { SubjectCreate, SubjectRow } from "../api/types";
import { useAuth } from "../auth/useAuth";
import HospitalSubmission from "../components/HospitalSubmission";

/* A site's patients on one study. Registration holds what a case report
   form may hold: a study code, initials, year of birth, sex, enrolment
   date. No name and no full date of birth; the code-to-person link stays
   in the site's own enrolment log. The code is namespaced by the site
   (BGH-…), typed or server-made, so a site cannot claim another site's
   patient. */

const SEXES = ["", "Female", "Male", "Other", "Unknown"];

interface Form {
  code: string;
  initials: string;
  birth_year: string;
  sex: string;
  enrolled_on: string;
  note: string;
}
const EMPTY: Form = { code: "", initials: "", birth_year: "", sex: "", enrolled_on: "", note: "" };

export default function Patients() {
  const id = Number(useParams().id);
  const { can, me } = useAuth();
  const [rows, setRows] = useState<SubjectRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<Form>(EMPTY);
  const [problem, setProblem] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setRows(await api.subjects(id)); setError(null); }
    catch (e) { setError((e as Error).message); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const prefix = me ? `${me.org.code}-` : "";
  const set = (patch: Partial<Form>) => { setForm((p) => ({ ...p, ...patch })); setProblem(null); };

  const register = async () => {
    const body: SubjectCreate = {};
    const code = form.code.trim().toUpperCase();
    if (code) {
      if (!code.startsWith(prefix)) { setProblem(`Subject IDs at this site start with ${prefix}`); return; }
      body.code = code;
    }
    const ini = form.initials.trim().toUpperCase();
    if (ini) {
      if (!/^[A-Z]{2,4}$/.test(ini)) { setProblem("Initials are 2 to 4 letters."); return; }
      body.initials = ini;
    }
    if (form.birth_year.trim()) {
      const y = Number(form.birth_year);
      const now = new Date().getFullYear();
      if (!Number.isInteger(y) || y < 1900 || y > now) { setProblem(`Year of birth must be between 1900 and ${now}.`); return; }
      body.birth_year = y;
    }
    if (form.sex) body.sex = form.sex;
    if (form.enrolled_on) body.enrolled_on = form.enrolled_on;
    if (form.note.trim()) body.note = form.note.trim();

    setBusy(true); setError(null);
    try {
      await api.createSubject(id, body);
      setForm(EMPTY); setOpen(false);
      await load();
    } catch (e) {
      setProblem((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!rows && !error) return <div className="page"><p className="muted">Loading…</p></div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Patients</h1>
        <div className="muted small">{me?.org.name} · subject IDs start with {prefix}</div>
      </div>

      {can("ecrf.submit") && rows && <HospitalSubmission protocolId={id} patientCount={rows.length} />}

      <div className="card">
        <div className="row row-between row-wrap">
          <p className="muted small">
            Synthetic data only. A patient is registered by study code, initials, year of birth and sex:
            never by name or full date of birth. The link from code to person is kept in the site's own enrolment log.
          </p>
          {can("subject.create") && !open && (
            <button type="button" className="btn btn-primary" onClick={() => setOpen(true)}>Register patient</button>
          )}
        </div>

        {open && (
          <div className="register">
            <label className="ctl">
              Subject ID
              <input className="input input-sm input-mono" value={form.code} placeholder={`${prefix}… (blank = next number)`}
                     onChange={(e) => set({ code: e.target.value })} aria-label="Subject ID" />
            </label>
            <label className="ctl">
              Initials
              <input className="input input-sm input-mono" value={form.initials} placeholder="JD" maxLength={4}
                     onChange={(e) => set({ initials: e.target.value })} aria-label="Initials" />
            </label>
            <label className="ctl">
              Year of birth
              <input className="input input-sm input-mono" type="number" min={1900} max={new Date().getFullYear()} value={form.birth_year}
                     onChange={(e) => set({ birth_year: e.target.value })} aria-label="Year of birth" />
            </label>
            <label className="ctl">
              Sex
              <select className="input input-sm" value={form.sex} onChange={(e) => set({ sex: e.target.value })} aria-label="Sex">
                {SEXES.map((x) => <option key={x} value={x}>{x || "—"}</option>)}
              </select>
            </label>
            <label className="ctl">
              Enrolled on
              <input className="input input-sm" type="date" value={form.enrolled_on} max={new Date().toISOString().slice(0, 10)}
                     onChange={(e) => set({ enrolled_on: e.target.value })} aria-label="Enrolment date" />
            </label>
            <label className="ctl ctl-wide">
              Note
              <input className="input input-sm input-grow" value={form.note} placeholder="optional, e.g. screened at clinic B"
                     onChange={(e) => set({ note: e.target.value })} aria-label="Note" />
            </label>
            <span className="grow" />
            {problem && <span className="error small">{problem}</span>}
            <button type="button" className="btn btn-primary btn-sm" onClick={register} disabled={busy}>{busy ? "Saving…" : "Register"}</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setOpen(false); setForm(EMPTY); setProblem(null); }}>Cancel</button>
          </div>
        )}
      </div>

      {rows && rows.length === 0 && (
        <div className="card"><p className="muted small">No patients yet. Register one to start entering data.</p></div>
      )}
      {rows && rows.length > 0 && (
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>Subject ID</th><th>Initials</th><th>Born</th><th>Sex</th><th>Enrolled</th>
                <th className="num">Readings</th><th>Registered</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono strong">{r.code}</td>
                  <td className="mono">{r.initials ?? "—"}</td>
                  <td className="mono">{r.birth_year ?? "—"}</td>
                  <td>{r.sex ?? "—"}</td>
                  <td className="mono small">{r.enrolled_on ?? "—"}</td>
                  <td className="num mono">{r.readings}</td>
                  <td className="small muted">{new Date(r.created_at).toLocaleDateString()} · {r.created_by}</td>
                  <td className="num"><Link className="btn btn-secondary btn-sm" to={`/site/s/${id}/patients/${encodeURIComponent(r.code)}`}>Enter data</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
