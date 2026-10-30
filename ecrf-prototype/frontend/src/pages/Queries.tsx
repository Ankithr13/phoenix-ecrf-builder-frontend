import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { QueryRow, QueryStatus } from "../api/types";
import { useAuth } from "../auth/useAuth";
import NewQuery from "../components/NewQuery";

const CHIP: Record<QueryStatus, string> = { open: "chip-rust", answered: "chip-amber", closed: "chip-teal" };

type Filter = "mine" | "open" | "answered" | "closed" | "";

/* One page for both portals. Queries run both ways: a sponsor questions a
   value a site entered, a site asks the sponsor about a value or the form.
   The other side answers; the side that raised it closes it. The server
   says per row whose turn it is (can_answer / can_close / for_me), so this
   page never has to know which side it is on. */
export default function Queries() {
  const { me } = useAuth();
  const [rows, setRows] = useState<QueryRow[] | null>(null);
  const [filter, setFilter] = useState<Filter>("mine");
  const [answers, setAnswers] = useState<Record<number, { text: string; value: string }>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);

  const load = useCallback(async () => {
    try { setRows(await api.queries()); setError(null); }
    catch (e) { setError((e as Error).message); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isSite = me?.org.type === "site";
  const pass = (q: QueryRow, f: Filter) => (f === "mine" ? q.for_me : !f || q.status === f);
  const shown = (rows ?? []).filter((q) => pass(q, filter));
  const draft = (id: number) => answers[id] ?? { text: "", value: "" };
  const setDraft = (id: number, patch: Partial<{ text: string; value: string }>) =>
    setAnswers((a) => ({ ...a, [id]: { ...draft(id), ...patch } }));

  const answer = async (q: QueryRow) => {
    const d = draft(q.id);
    if (!d.text.trim()) return;
    setBusy(q.id); setError(null);
    try {
      await api.answerQuery(q.id, d.text.trim(), isSite && d.value.trim() ? d.value.trim() : undefined);
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

  const who = (org: "sponsor" | "site") => (org === "sponsor" ? "sponsor" : "site");

  if (!rows && !error) return <div className="page"><p className="muted">Loading…</p></div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Queries</h1>
        <div className="row row-wrap">
          <div className="muted small">
            {isSite
              ? "Questions from the sponsor about values entered here, and questions this site has asked the sponsor"
              : "Questions raised about entered values, from either side. The side that asked closes it once satisfied."}
          </div>
          {!composing && <button type="button" className="btn btn-primary" onClick={() => setComposing(true)}>New query</button>}
        </div>
      </div>

      {composing && (
        <div className="mb-3">
          <NewQuery onDone={() => { setComposing(false); setFilter(""); load(); }} onCancel={() => setComposing(false)} />
        </div>
      )}

      <div className="row row-wrap mb-3">
        {(["mine", "open", "answered", "closed", ""] as const).map((f) => (
          <button key={f || "all"} type="button" className={`tab${filter === f ? " active" : ""}`} onClick={() => setFilter(f)}>
            {f === "mine" ? "my turn" : f || "all"}
            <span className="tab-count">{(rows ?? []).filter((q) => pass(q, f)).length}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 && <div className="card"><p className="muted small">Nothing here.</p></div>}

      {shown.map((q) => (
        <div className="card" key={q.id}>
          <div className="row row-between row-wrap">
            <div className="row row-wrap">
              <span className={`pill ${CHIP[q.status]}`}>{q.status}</span>
              <span className="pill">asked by {who(q.raised_by_org)}</span>
              <span className="pill chip-brand">about {q.about === "value" ? "a value" : q.about === "study" ? "the study" : `a ${q.about}`}</span>
              {q.subject && <span className="mono">{q.subject}</span>}
              {q.visit && <><span className="muted">·</span><span>{q.visit}</span></>}
              {q.field && (
                <>
                  <span className="muted">·</span>
                  <span className="strong">{q.field}{(q.repeat ?? 1) > 1 ? ` · ${q.repeat}` : ""}</span>
                  <span className="muted">=</span>
                  <span className="mono">{q.value ?? "—"}</span>
                </>
              )}
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

          {q.can_answer && (
            <div className="row row-wrap mt-3 query-reply">
              <input className="input grow" placeholder="Your answer" value={draft(q.id).text} onChange={(e) => setDraft(q.id, { text: e.target.value })} />
              {isSite && q.about === "value" && (
                <input className="input input-mono query-value" placeholder="Corrected value (optional)" value={draft(q.id).value} onChange={(e) => setDraft(q.id, { value: e.target.value })} />
              )}
              <button type="button" className="btn btn-primary btn-sm" onClick={() => answer(q)} disabled={busy === q.id || !draft(q.id).text.trim()}>
                {busy === q.id ? "Sending…" : q.status === "answered" ? "Answer again" : "Answer"}
              </button>
            </div>
          )}
          {q.can_close && (
            <div className="row mt-3">
              <button type="button" className="btn btn-teal btn-sm" onClick={() => close(q)} disabled={busy === q.id}>
                {busy === q.id ? "Closing…" : "Close query"}
              </button>
              <span className="small muted">
                {q.status === "open" ? "Waiting for the other side to answer. " : ""}
                {q.about === "value" ? "Closing returns the value to awaiting review, so it is approved again on purpose." : "Close it once the answer settles the question."}
              </span>
            </div>
          )}
        </div>
      ))}

      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
