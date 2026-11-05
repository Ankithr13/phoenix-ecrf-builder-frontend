import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { HospitalSubmissionStatus } from "../api/types";
import "../styles/notifications.css";

export default function HospitalSubmission({ protocolId, patientCount }: { protocolId: number; patientCount: number }) {
  const [submission, setSubmission] = useState<HospitalSubmissionStatus | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true);
    setConfirmed(false);
    try { setSubmission(await api.hospitalSubmission(protocolId)); setError(null); }
    catch (failure) { setError((failure as Error).message); setSubmission(null); }
    finally { setLoading(false); }
  }, [protocolId]);
  useEffect(() => { void refresh(); setConfirmed(false); }, [refresh, patientCount]);

  const submit = async () => {
    if (!confirmed) return;
    setBusy(true); setError(null);
    try {
      setSubmission(await api.submitHospitalEcrf(protocolId));
      setConfirmed(false);
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  };

  return <section className="card hospital-submission" aria-labelledby="hospital-submission-title">
    <div className="row row-between row-wrap"><h2 id="hospital-submission-title" className="section-title">Submit your hospital’s entire eCRF</h2><button className="btn btn-secondary btn-sm" type="button" onClick={refresh} disabled={busy || loading}>Refresh submission status</button></div>
    <p className="muted small mt-2">This covers all patients and visits on this assigned eCRF—not just one patient or visit. Submitting tells the sponsor your hospital considers the work ready for review. It does not approve or lock the data.</p>
    {loading && <p className="muted small mt-3" role="status">Checking submission status…</p>}
    {!loading && submission?.state === "submitted" && <p className="hospital-submitted" role="status">Your hospital has submitted this eCRF for sponsor review.{submission.submitted_at && <> Submitted {new Date(submission.submitted_at).toLocaleString()} by {submission.submitted_by}.</>}</p>}
    {!loading && submission?.state === "changed" && <p className="hospital-submission-changed" role="status">Patient or saved data has changed since the previous submission. Review the changes and submit again when your hospital’s entire eCRF is ready.</p>}
    {!loading && submission && submission.state !== "submitted" && <>
      {!submission.can_submit && <p className="muted small mt-3">Register patients and save data before submitting.</p>}
      <label className="check mt-3"><input type="checkbox" checked={confirmed} disabled={!submission.can_submit || busy} onChange={(event) => setConfirmed(event.target.checked)} /><span>I confirm my hospital’s entire assigned eCRF is ready for sponsor review.</span></label>
      <button className="btn btn-teal btn-sm mt-3" type="button" disabled={!confirmed || !submission.can_submit || busy} onClick={submit}>{busy ? "Submitting…" : "Submit entire eCRF for review"}</button>
    </>}
    <p className="muted small mt-3">If you add patients or change saved data later, you will need to submit the updated eCRF again.</p>
    {error && <p className="error small mt-3" role="alert">{error}</p>}
  </section>;
}
