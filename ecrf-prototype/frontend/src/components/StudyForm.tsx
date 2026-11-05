import { useId, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { SponsorStudy } from "../api/types";

export default function StudyForm({ onCreated, onCancel }: { onCreated: (study: SponsorStudy) => void; onCancel: () => void }) {
  const formId = useId();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const study = await api.createStudy({ name: name.trim(), code: code.trim() });
      onCreated(study);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card study-create" onSubmit={submit} aria-labelledby={`${formId}-title`}>
      <h2 className="section-title" id={`${formId}-title`}>Create a study</h2>
      <p className="muted small mb-4">Use the study ID agreed with your team. Protocols will be assigned manually.</p>
      <div className="grid-2">
        <div>
          <label className="label" htmlFor={`${formId}-name`}>Study name</label>
          <input className="input" id={`${formId}-name`} value={name} onChange={(event) => setName(event.target.value)} maxLength={200} required disabled={busy} autoFocus />
        </div>
        <div>
          <label className="label" htmlFor={`${formId}-code`}>Study ID</label>
          <input className="input" id={`${formId}-code`} value={code} onChange={(event) => setCode(event.target.value)} maxLength={64} pattern="[A-Za-z0-9][A-Za-z0-9._/\-]*" placeholder="e.g. PHX-401-201" required disabled={busy} />
        </div>
      </div>
      {error && <p className="error mt-3" role="alert">{error}</p>}
      <div className="row mt-4">
        <button className="btn btn-teal" type="submit" disabled={busy || !name.trim() || !code.trim()}>{busy ? "Creating…" : "Create study"}</button>
        <button className="btn btn-secondary" type="button" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}
