import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { QueryRow, QueryStatus } from "../api/types";
import { useAuth } from "../auth/useAuth";

const CHIP: Record<QueryStatus, string> = { open: "chip-rust", answered: "chip-amber", closed: "chip-teal" };

/* One page for both portals. A site sees queries on its own patients and
   answers them, optionally with a corrected value. A sponsor sees queries
   on its protocols and closes them once satisfied. */
export default function Queries() {
  const { me, can } = useAuth();
  const [rows, setRows] = useState<QueryRow[] | null>(null);
  const [filter, setFilter] = useState<string>(me?.org.type === "site" ? "open" : "answered");
  const [answers, setAnswers] = useState<Record<number, { text: string; value: string }>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setRows(await api.queries()); setError(null); }
    catch (e) { setError((e as Error).message); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const shown = (rows ?? []).filter((q) => !filter || q.status === filter);
  const draft = (id: number) => answers[id] ?? { text: "", value: "" };
  const setDraft = (id: number, patch: Partial<{ text: string; value: string }>) =>
    setAnswers((a) => ({ ...a, [id]: { ...draft(id), ...patch } }));

  const answer = async (q: QueryRow) => {
    const d = draft(q.id);
    if (!d.text.trim()) return;
    setBusy(q.id); setError(null);
    try {
      await api.answerQuery(q.id, d.text.trim(), d.value.trim() || undefined);
      setAnswers((a) => { const n = { ...a }; delete n[q.id]; return n; });
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  };

  const close = async (q: QueryRow) => {
    setBusy(q.id); setError(null);
    try { await api.closeQuery(q.id); await load(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  };

  if (!rows && !error) return <div className="page"><p className="muted">Loading…</p></div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Queries</h1>
        <div className="muted small">
          {me?.org.type === "site"
            ? "Questions the sponsor has raised about values entered at this site"
            : "Questions raised about entered values; close one once the answer satisfies you"}
        </div>
      </div>

      <div className="row row-wrap mb-3">
        {(["open", "answered", "closed", ""] as const).map((f) => (
          <button key={f || "all"} type="button" className={`tab${filter === f ? " active" : ""}`} onClick={() => setFilter(f)}>
            {f || "all"}<span className="tab-count">{(rows ?? []).filter((q) => !f || q.status === f).length}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 && <div className="card"><p className="muted small">Nothing here.</p></div>}

      {shown.map((q) => (
        <div className="card" key={q.id}>
          <div className="row row-between row-wrap">
            <div className="row row-wrap">
              <span className={`pill ${CHIP[q.status]}`}>{q.status}</span>
              <span className="mono">{q.subject}</span>
              <span className="muted">·</span>
              <span>{q.visit}</span>
              <span className="muted">·</span>
              <span className="strong">{q.field}{q.repeat > 1 ? ` · ${q.repeat}` : ""}</span>
              <span className="muted">=</span>
              <span className="mono">{q.value ?? "—"}</span>
            </div>
            <div className="small muted">{q.protocol_name}{q.site ? ` · ${q.site}` : ""}</div>
          </div>

          <div className="query-thread mt-3">
            <div className="query-msg">
              <div className="xs muted">{q.raised_by} · {new Date(q.raised_at).toLocaleString()}</div>
              <div>{q.text}</div>
            </div>
            {q.answer_text && (
              <div className="query-msg query-answer">
                <div className="xs muted">{q.answered_by} · {q.answered_at && new Date(q.answered_at).toLocaleString()}</div>
                <div>{q.answer_text}</div>
              </div>
            )}
            {q.status === "closed" && (
              <div className="xs muted">closed by {q.closed_by}{q.closed_at && ` · ${new Date(q.closed_at).toLocaleString()}`}</div>
            )}
          </div>

          {q.status !== "closed" && can("query.answer") && (
            <div className="row row-wrap mt-3 query-reply">
              <input className="input grow" placeholder="Your answer" value={draft(q.id).text} onChange={(e) => setDraft(q.id, { text: e.target.value })} />
              <input className="input input-mono query-value" placeholder="Corrected value (optional)" value={draft(q.id).value} onChange={(e) => setDraft(q.id, { value: e.target.value })} />
              <button type="button" className="btn btn-primary btn-sm" onClick={() => answer(q)} disabled={busy === q.id || !draft(q.id).text.trim()}>
                {busy === q.id ? "Sending…" : q.status === "answered" ? "Answer again" : "Answer"}
              </button>
            </div>
          )}
          {q.status !== "closed" && can("query.close") && (
            <div className="row mt-3">
              <button type="button" className="btn btn-teal btn-sm" onClick={() => close(q)} disabled={busy === q.id}>
                {busy === q.id ? "Closing…" : "Close query"}
              </button>
              <span className="small muted">Closing returns the value to awaiting review, so it is approved again on purpose.</span>
            </div>
          )}
        </div>
      ))}

      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
