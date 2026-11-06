import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link, useBlocker, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { DraftResponse, FieldChange, FieldDef, VersionRow } from "../api/types";
import FieldCard from "../components/FieldCard";
import Stat from "../components/Stat";
import { useAuth } from "../auth/useAuth";
import ReviewDialog from "../components/ReviewDialog";
import { NavigationContext } from "../navigation/context";
import "../styles/review-workflow.css";

type SectionView = { number: string; title: string; page: number | null; text: string; located_by?: "number" | "title" | "text" };

/* PDF text comes hard-wrapped with running headers and footers in it.
   Rebuild paragraphs: a bullet ("o ", "•", "-") or a numbered line starts
   a new block, a short line ending in a full stop ends one, and footer
   lines like "9 | P a g e 26 Feb 2019" or "Confidential Page 31" go. */
function formatSection(text: string): { kind: "p" | "li" | "h"; text: string }[] {
  const junk = /^(\d+\s*\|\s*P\s*a\s*g\s*e.*|.*\bPage\s*\d+\s*(of\s*\d+)?\s*$|Confidential.*|Version\s*Date.*|CONFIDENTIAL.*)$/i;
  const bullet = /^\s*(?:[o•\-–▪■]|\(?[a-z0-9]{1,3}[.)])\s+(.*)$/;
  const heading = /^[A-Z][A-Za-z /&-]{2,60}$/;
  const out: { kind: "p" | "li" | "h"; text: string }[] = [];
  let buf = "";
  const flush = () => { if (buf.trim()) out.push({ kind: "p", text: buf.trim() }); buf = ""; };
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || junk.test(line)) continue;
    const b = bullet.exec(line);
    if (b) { flush(); out.push({ kind: "li", text: b[1] }); continue; }
    if (heading.test(line) && line.split(" ").length <= 8 && !/[.:;]$/.test(line)) { flush(); out.push({ kind: "h", text: line }); continue; }
    const last = out[out.length - 1];
    if (!buf && last && last.kind === "li" && /^[a-z(]/.test(line)) { last.text += " " + line; continue; }
    buf += (buf ? " " : "") + line;
    if (/[.!?]$/.test(line) && line.length < 70) flush();
  }
  flush();
  return out;
}

const key = (visit: string, name: string) => `${visit}\u0000${name}`;

export default function Review() {
  const { id } = useParams();
  return <ReviewEditor key={id} id={Number(id)} />;
}

function ReviewEditor({ id }: { id: number }) {
  const navigate = useNavigate();
  const navigation = useContext(NavigationContext);
  const registerLeaveGuard = navigation?.registerLeaveGuard;
  const { can } = useAuth();
  const [resp, setResp] = useState<DraftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [changes, setChanges] = useState<Record<string, FieldChange>>({});
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [section, setSection] = useState<{ loading: boolean; data: SectionView | null; error: string | null } | null>(null);
  const [versions, setVersions] = useState<VersionRow[] | null>(null);
  const [locking, setLocking] = useState(false);
  const [fStatus, setFStatus] = useState<"all" | "needs" | "draft" | "flagged" | "approved" | "rejected">("all");
  const [fIssue, setFIssue] = useState<string>("");
  const [fSuggest, setFSuggest] = useState<"" | "protocol" | "library" | "heuristic" | "none">("");
  const [fText, setFText] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [editors, setEditors] = useState<string[]>([]);
  const [editorReset, setEditorReset] = useState(0);
  const [needsReload, setNeedsReload] = useState(false);
  const [confirmation, setConfirmation] = useState<"lock" | "discard" | "approve_all_remaining" | "approve_suggested" | "guesses" | null>(null);
  const [externalExit, setExternalExit] = useState<(() => void) | null>(null);
  const [queuedExit, setQueuedExit] = useState<(() => void) | null>(null);
  const inFlight = useRef(false);
  const busy = saving || locking;
  const pending = Object.keys(changes).length;
  const dirty = pending > 0 || note.length > 0 || editors.length > 0;
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    (dirty || busy) && (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search));

  useEffect(() => {
    if (!dirty && !busy) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, busy]);

  useEffect(() => {
    registerLeaveGuard?.((action) => {
      if (dirty || busy) setExternalExit(() => action);
      else action();
    });
    return () => registerLeaveGuard?.(null);
  }, [registerLeaveGuard, dirty, busy]);

  useEffect(() => {
    if (!queuedExit || dirty || busy) return;
    setQueuedExit(null);
    queuedExit();
  }, [queuedExit, dirty, busy]);

  const editingChanged = useCallback((editorId: string, editing: boolean) => {
    setEditors((previous) => {
      if (editing === previous.includes(editorId)) return previous;
      return editing ? [...previous, editorId] : previous.filter((existing) => existing !== editorId);
    });
  }, []);

  const load = useCallback(async () => {
    try {
      const r = await api.draft(id);
      setResp(r);
      setError(null);
      setNeedsReload(false);
      setActive((a) => (a && r.draft?.forms.some((f) => f.visit === a) ? a : r.draft?.forms[0]?.visit ?? null));
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const loadVersions = async () => {
    try { setVersions(await api.versions(id)); }
    catch (e) { setError((e as Error).message); }
  };

  const onChange = (visit: string, name: string, change: Partial<FieldChange>) => {
    setMessage(null);
    setChanges((prev) => {
      const k = key(visit, name);
      return { ...prev, [k]: { ...(prev[k] ?? { visit, name }), ...change } };
    });
  };

  const save = async (action: "save" | "approve_all_remaining" | "approve_suggested", includeGuesses = false) => {
    if (inFlight.current || editors.length > 0 || needsReload) return false;
    inFlight.current = true;
    setSaving(true); setError(null); setMessage(null);
    try {
      await api.review(id, Object.values(changes), note.trim() || undefined, action, includeGuesses);
      setChanges({});
      setNote("");
      setNeedsReload(true);
      const refreshed = await load();
      setMessage(refreshed ? "Draft saved. Saving does not lock the form or grant hospitals access." : "Your draft was saved, but its latest details could not be loaded. Retry loading before editing again.");
      if (versions) await loadVersions();
      return refreshed;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };

  const lock = async () => {
    if (inFlight.current || dirty || needsReload) return;
    inFlight.current = true;
    setLocking(true); setError(null); setMessage(null); setConfirmation(null);
    try {
      await api.lock(id);
      setNeedsReload(true);
      const refreshed = await load();
      setMessage(refreshed ? "Form finalized and locked. Manage hospital access in Sites." : "The form was locked, but its latest details could not be loaded. Retry loading to view it.");
      if (versions) await loadVersions();
    }
    catch (e) { setError((e as Error).message); }
    finally { inFlight.current = false; setLocking(false); }
  };

  const discard = () => {
    setChanges({}); setNote(""); setEditors([]);
    setEditorReset((previous) => previous + 1);
    setMessage("Unsaved edits discarded. The uploaded protocol and saved versions are unchanged.");
    setError(null);
    setConfirmation(null);
  };
  const stay = () => {
    if (blocker.state === "blocked") blocker.reset();
    setExternalExit(null);
    setConfirmation(null);
  };
  const finishExit = () => {
    if (blocker.state === "blocked") blocker.proceed();
    else if (externalExit) setQueuedExit(() => externalExit);
    setExternalExit(null);
  };
  const saveAndExit = async () => {
    if (!dirty || await save("save")) {
      if (blocker.state === "blocked" || externalExit) finishExit();
      else setQueuedExit(() => () => navigate("/sponsor/ecrfs?stage=needs_review"));
    }
  };

  const showSection = async (n: string) => {
    setSection({ loading: true, data: null, error: null });
    try { setSection({ loading: false, data: await api.section(id, n), error: null }); }
    catch (e) { setSection({ loading: false, data: null, error: (e as Error).message }); }
  };

  const draft = resp?.draft ?? null;
  const form = useMemo(() => draft?.forms.find((f) => f.visit === active) ?? null, [draft, active]);

  // Merge pending local edits into the field so the card reflects them.
  const merged = (f: FieldDef, visit: string): FieldDef => {
    const c = changes[key(visit, f.name)];
    if (!c) return f;
    return {
      ...f,
      name: c.new_name ?? f.name,
      type: c.type ?? f.type,
      unit: c.unit !== undefined ? c.unit : f.unit,
      status: c.status ?? f.status,
      min: c.min !== undefined ? c.min : f.min,
      max: c.max !== undefined ? c.max : f.max,
      required: c.required ?? f.required,
      repeats: c.repeats ?? f.repeats,
      choices: c.choices !== undefined ? c.choices : f.choices,
    };
  };

  if (!resp && !error) return <div className="page"><p className="muted">Loading…</p></div>;

  if (resp && !draft) {
    return (
      <div className="page">
        <h1 className="page-title">{resp.protocol.name}</h1>
        <div className="card">
          <p className="strong">Not extracted yet</p>
          <p className="muted small mt-2">Run the extraction pipeline to produce a draft eCRF for review.</p>
          {can("protocol.extract") && <Link className="btn btn-primary mt-4" to={`/sponsor/p/${id}/visits`}>Find visits and extract</Link>}
        </div>
        {error && <p className="error mt-3">{error}</p>}
      </div>
    );
  }

  if (!resp || !draft) {
    return <div className="page">{error && <p className="error">{error}</p>}</div>;
  }

  const s = draft.summary;
  const sugg = resp.library_suggestions ?? {};
  const locked = resp.state === "locked";
  const pendingSuggested = (from: "library" | "heuristic") => draft.forms.reduce(
    (n, f) => n + f.fields.filter((x) => x.status === "flagged" && x.issue === "missing" && x.suggested?.length && x.suggested_from === from).length, 0);
  const suggestedCount = pendingSuggested("library");
  const guessedCount = pendingSuggested("heuristic");

  // The filter bar works on the active visit's fields, after pending
  // local edits are merged in, so a field you just approved moves out of
  // "needs a decision" immediately.
  const matches = (f: FieldDef): boolean => {
    const st = f.status;
    if (fStatus === "needs" && st !== "draft" && st !== "flagged") return false;
    if (fStatus !== "all" && fStatus !== "needs" && st !== fStatus) return false;
    if (fIssue && f.issue !== fIssue) return false;
    if (fSuggest === "none" && f.suggested?.length) return false;
    if ((fSuggest === "protocol" || fSuggest === "library" || fSuggest === "heuristic") && f.suggested_from !== fSuggest) return false;
    if (fText && !`${f.name} ${f.cdash ?? ""} ${f.source.quote}`.toLowerCase().includes(fText.toLowerCase())) return false;
    return true;
  };
  const visible = form
    ? form.fields.map((f) => ({ original: f.name, field: merged(f, form.visit) })).filter((x) => matches(x.field))
    : [];
  const countBy = (pred: (f: FieldDef) => boolean) => (form ? form.fields.map((f) => merged(f, form.visit)).filter(pred).length : 0);
  const blockers = resp.lock_blockers ?? { draft: 0, flagged: 0 };
  const left = blockers.draft + blockers.flagged;
  const editorOpen = editors.length > 0;
  const controlsDisabled = busy || needsReload;
  const leaving = blocker.state === "blocked" || externalExit !== null;
  const fieldCounts = draft.forms.flatMap((visit) => visit.fields.map((field) => merged(field, visit.visit)))
    .reduce((counts, field) => ({ ...counts, [field.status]: counts[field.status] + 1 }), { draft: 0, flagged: 0, approved: 0, rejected: 0 });

  return (
    <div className="page">
      <div className="page-head">
        <Link className="inline small" to="/sponsor/ecrfs">← eCRF Management</Link>
        <h1 className="page-title">{resp.protocol.name}</h1>
        <section className="card review-workflow" aria-label="Review progress">
          <h2 className="section-title">{locked ? "Locked eCRF" : left > 0 || dirty ? "Draft — review incomplete" : "Draft — ready to finalize"}</h2>
          <p className="muted small">Review each visit, apply your edits, then save a draft or finalize once every field has a decision. Drafts stay available in Studies and eCRF Management.</p>
          <div className="review-workflow-counts">
            <span className="pill">v{resp.version}</span>
            <span className="pill">{fieldCounts.draft} draft</span>
            <span className="pill chip-amber">{fieldCounts.flagged} flagged</span>
            <span className="pill chip-teal">{fieldCounts.approved} approved</span>
            <span className="pill">{fieldCounts.rejected} rejected</span>
          </div>
          <p className="muted small">Counts include applied, unsaved edits. Finalization uses the saved version.</p>
          {resp.created_at && <p className="muted small">Version saved {new Date(resp.created_at).toLocaleString()} by {resp.created_by}</p>}
          {message && <p className="small mt-3" role="status">{message}</p>}
          {needsReload && <button className="btn btn-secondary mt-3" type="button" onClick={() => void load()} disabled={busy}>Retry loading saved form</button>}
          {editorOpen && <p className="review-editor-hint small" role="status">Apply or cancel the open field editor before saving, changing visits or filtering. Applied edits still need Save draft.</p>}
          {!locked && can("form.edit") && <div className="review-workflow-actions">
            <button type="button" className="btn btn-primary" onClick={() => void save("save")} disabled={controlsDisabled || editorOpen || !dirty}>{saving ? "Saving…" : "Save draft"}</button>
            <button type="button" className="btn btn-secondary" onClick={() => void saveAndExit()} disabled={controlsDisabled || editorOpen}>Save draft & exit</button>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirmation("discard")} disabled={busy || !dirty}>Discard unsaved changes</button>
          </div>}
          {locked && can("site.assign") && <Link className="btn btn-secondary mt-3" to={`/sponsor/p/${id}/sites`}>Manage hospital access</Link>}
        </section>
        <details className="panel mb-4"><summary>Extraction details</summary><div className="panel-body">
        <div className="row row-wrap row-between">
          <div className="mono small muted">
            v{resp.version} · {draft.backend} · {draft.model} · hash {resp.protocol.hash} · threshold {s.threshold}
            {s.est_cost_usd !== undefined && (
              <> · {s.llm_calls_made} call{s.llm_calls_made === 1 ? "" : "s"}{s.llm_calls_from_cache ? ` + ${s.llm_calls_from_cache} cached` : ""} · ${s.est_cost_usd.toFixed(4)}{s.strategy ? ` · ${s.strategy}` : ""}</>
            )}
          </div>
        </div>
        </div></details>
          {!locked && can("form.lock") && (
            <div className="row">
              {left > 0 && (
                <span className="small muted">
                  {blockers.draft > 0 && `${blockers.draft} draft`}
                  {blockers.draft > 0 && blockers.flagged > 0 && ", "}
                  {blockers.flagged > 0 && `${blockers.flagged} flagged`} still need a decision
                </span>
              )}
              <button
                type="button" className="btn btn-teal btn-sm" onClick={() => setConfirmation("lock")}
                disabled={controlsDisabled || left > 0 || dirty}
                title={dirty ? "Apply and save your pending changes first" : left > 0 ? "Every field must be approved or rejected first" : "Freeze this version for sites"}
              >
                {locking ? "Locking…" : "Finalize & lock"}
              </button>
            </div>
          )}
      </div>

      {!locked && can("form.lock") && (resp.lock_warnings ?? []).length > 0 && (
        <div className="card warn-card">
          <p className="strong">Before you lock</p>
          <p className="muted small">These will not stop the lock, but a site will run into them. Edit the field, or lock anyway if it is deliberate.</p>
          <ul className="warn-list">
            {(resp.lock_warnings ?? []).map((w) => (
              <li key={w.kind}>
                <span className="strong">{w.count}</span> {w.text}
                <details className="inline-details"><summary className="btn-link small">which</summary>
                  <div className="small muted mono">{w.fields.join(" · ")}</div>
                </details>
              </li>
            ))}
          </ul>
        </div>
      )}

      {locked && (
        <div className="lock-banner">
          <span className="strong">Locked</span>
          <span>by {resp.locked_by}{resp.locked_at && <> on {new Date(resp.locked_at).toLocaleString()}</>}. This version is frozen; sites enter data against it and nothing here can change.</span>
        </div>
      )}

      <details className="panel mb-4">
        <summary>Verification results & dropped fields ({draft.rejections.length})</summary>
        <div className="panel-body">
      <div className="grid-3">
        <Stat label="Fields kept" value={s.fields_kept} sub={`of ${s.fields_generated} generated across ${s.visits} visits`} />
        <Stat label="Dropped by verification" value={s.rejected} tone={s.rejected > 0 ? "rust" : "default"} sub="quote not found in protocol" />
        <Stat label="Flagged for review" value={s.flagged} tone={s.flagged > 0 ? "amber" : "default"} sub="model reported an issue" />
      </div>

      {draft.rejections.length > 0 && (
        <div className="card card-rust mt-4">
          <div className="section-title">Dropped by verification</div>
          <p className="small mb-3">
            These quotes were not found in the protocol. The fields were deleted before review.
            This is the grounding check working.
          </p>
          {draft.rejections.map((r, i) => (
            <div className="reject-row" key={i}>
              <div className="mono">{r.visit}</div>
              <div className="strong">{r.name}</div>
              <div>
                <div className="italic">"{r.quote}"</div>
                <div className="row row-wrap mt-2 xs">
                  <span className="mono">§{r.section}</span>
                  <span className="mono">{r.score}%</span>
                  <span className="muted">{r.reason}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

        </div>
      </details>

      <div className="mt-5">
        <div className="tabs" role="tablist">
          {draft.forms.map((f) => (
            <button
              key={f.visit}
              type="button"
              role="tab"
              aria-selected={f.visit === active}
              className={`tab${f.visit === active ? " active" : ""}`}
              disabled={editorOpen || controlsDisabled}
              onClick={() => setActive(f.visit)}
            >
              {f.visit}<span className="tab-count">{f.fields.length}</span>
            </button>
          ))}
        </div>

        {form && (
          <>
            {form.fields.length === 0 && <p className="muted">No fields survived verification for this visit.</p>}
            {form.fields.length > 0 && (
              <fieldset className="filter-bar review-controls" disabled={editorOpen || controlsDisabled}>
                <div className="row row-wrap">
                  {([
                    ["all", "All", () => true],
                    ["needs", "Needs a decision", (f: FieldDef) => f.status === "draft" || f.status === "flagged"],
                    ["flagged", "Flagged", (f: FieldDef) => f.status === "flagged"],
                    ["draft", "Draft", (f: FieldDef) => f.status === "draft"],
                    ["approved", "Approved", (f: FieldDef) => f.status === "approved"],
                    ["rejected", "Rejected", (f: FieldDef) => f.status === "rejected"],
                  ] as const).map(([key, label, pred]) => (
                    <button key={key} type="button" className={`tab${fStatus === key ? " active" : ""}`} onClick={() => setFStatus(key)}>
                      {label}<span className="tab-count">{countBy(pred)}</span>
                    </button>
                  ))}
                </div>
                <div className="row row-wrap mt-2">
                  <select className="input filter-select" value={fIssue} onChange={(e) => setFIssue(e.target.value)} aria-label="Issue">
                    <option value="">Any issue</option>
                    <option value="missing">missing</option>
                    <option value="conflicting">conflicting</option>
                    <option value="ambiguous">ambiguous</option>
                    <option value="unsupported">unsupported</option>
                    <option value="none">no issue</option>
                  </select>
                  <select className="input filter-select" value={fSuggest} onChange={(e) => setFSuggest(e.target.value as typeof fSuggest)} aria-label="Suggestion">
                    <option value="">Any source</option>
                    <option value="protocol">found in protocol</option>
                    <option value="library">suggested by library</option>
                    <option value="heuristic">range guessed</option>
                    <option value="none">nothing suggested</option>
                  </select>
                  <input className="input filter-text" placeholder="Search name, code or quote" value={fText} onChange={(e) => setFText(e.target.value)} />
                  <span className="small muted">{visible.length} of {form.fields.length}</span>
                  {(fStatus !== "all" || fIssue || fSuggest || fText) && (
                    <button type="button" className="btn-link" onClick={() => { setFStatus("all"); setFIssue(""); setFSuggest(""); setFText(""); }}>clear</button>
                  )}
                </div>
              </fieldset>
            )}
            {form.fields.length > 0 && visible.length === 0 && <p className="muted small">No fields match the filter.</p>}
            {visible.map(({ original, field: f }) => (
              <FieldCard
                key={`${editorReset}-${form.visit}-${original}`}
                field={f}
                onChange={(c) => onChange(form.visit, original, c)}
                onShowSection={showSection}
                readOnly={locked || !can("form.edit") || controlsDisabled}
                editorId={key(form.visit, original)}
                onEditingChange={editingChanged}
              />
            ))}

            <details className="panel mt-4">
              <summary>Library also defines… <span className="mono muted-2">{(sugg[form.visit] ?? []).length}</span></summary>
              <div className="panel-body">
                <p className="muted small mb-3">
                  Standard fields from the CDASH library not found in this protocol. Not grounded. Shown for reference only.
                </p>
                <div className="row row-wrap">
                  {(sugg[form.visit] ?? []).map((x) => (
                    <span className="pill" key={x.cdash}>{x.name} · {x.cdash}</span>
                  ))}
                  {(sugg[form.visit] ?? []).length === 0 && <span className="muted small">Nothing further.</span>}
                </div>
              </div>
            </details>
          </>
        )}
      </div>

      <details className="panel mt-4" onToggle={(e) => { if ((e.target as HTMLDetailsElement).open && !versions) loadVersions(); }}>
        <summary>Version history</summary>
        <div className="panel-body">
          {!versions && <p className="muted small">Loading…</p>}
          {versions && versions.map((v) => (
            <div className="mono small row row-wrap" key={v.version} style={{ padding: "var(--s-1) 0" }}>
              <span>v{v.version}</span>
              <span className="muted">·</span>
              <span>{v.note ?? "—"}</span>
              <span className="muted">·</span>
              <span>{v.created_by}</span>
              <span className="muted">·</span>
              <span className="muted">{new Date(v.created_at).toLocaleString()}</span>
            </div>
          ))}
        </div>
      </details>

      {error && <p className="error mt-3" role="alert">{error}</p>}

      {can("form.edit") && !locked && <div className="sticky-bar review-save-bar">
        <span className="small muted">
          <span className="mono">{pending}</span> pending change{pending === 1 ? "" : "s"}
        </span>
        <input
          className="input grow"
          placeholder="Review note (optional)"
          aria-label="Review note (optional)"
          value={note}
          disabled={controlsDisabled}
          onChange={(e) => { setNote(e.target.value); setMessage(null); }}
        />
        <button type="button" className="btn btn-primary" onClick={() => void save("save")} disabled={controlsDisabled || editorOpen || !dirty}>
          {saving ? "Saving…" : "Save draft"}
        </button>
        {suggestedCount > 0 && (
          <button
            type="button" className="btn btn-secondary" onClick={() => setConfirmation("approve_suggested")} disabled={controlsDisabled || editorOpen}
            title="Flagged only because the protocol gave no unit, range or choices and the CDASH library has a standard one. Approving accepts the library's values."
          >
            Accept {suggestedCount} library suggestion{suggestedCount === 1 ? "" : "s"}
          </button>
        )}
        {guessedCount > 0 && (
          <button
            type="button" className="btn btn-secondary" onClick={() => setConfirmation("guesses")} disabled={controlsDisabled || editorOpen}
            title="Also approves fields whose range was guessed from the unit or name. Look at them first: they are plausibility limits, not clinical ranges."
          >
            Accept {guessedCount} guessed range{guessedCount === 1 ? "" : "s"} too
          </button>
        )}
        <button type="button" className="btn btn-secondary" onClick={() => setConfirmation("approve_all_remaining")} disabled={controlsDisabled || editorOpen || fieldCounts.draft === 0}>
          Approve remaining draft fields
        </button>
      </div>}

      {(leaving || confirmation) && <ReviewDialog title={leaving ? "Leave this review?" : confirmation === "lock" ? "Finalize and lock this form?" : confirmation === "discard" ? "Discard unsaved changes?" : "Confirm bulk approval"} onStay={stay}>
        {leaving ? <>
          <p>{busy ? "A save or lock is in progress. Wait until it finishes before leaving." : "You have unsaved review work. Save a draft to continue later, discard only unsaved changes, or stay here."}</p>
          {editorOpen && <p className="review-editor-hint small">Choose Stay, then apply or cancel the open field editor before saving. Discard will also remove edits still inside that editor.</p>}
          <div className="review-dialog-actions">
            <button type="button" className="btn btn-secondary" onClick={stay} autoFocus>Stay</button>
            <button type="button" className="btn btn-primary" onClick={() => void saveAndExit()} disabled={controlsDisabled || editorOpen || !can("form.edit")}>Save draft & leave</button>
            <button type="button" className="btn btn-danger" onClick={() => { discard(); finishExit(); }} disabled={busy}>Discard changes & leave</button>
          </div>
        </> : confirmation === "discard" ? <>
          <p>This removes only edits since your last save, including any open field editor. It does not delete the protocol or any saved version.</p>
          <div className="review-dialog-actions"><button type="button" className="btn btn-secondary" onClick={stay} autoFocus>Keep editing</button><button type="button" className="btn btn-danger" onClick={discard} disabled={busy}>Discard unsaved changes</button></div>
        </> : confirmation === "lock" ? <>
          <p>Lock saved version {resp.version} of {resp.protocol.name}. This freezes the form and prevents further edits. Hospital assignments are managed separately in Sites.</p>
          <p className="muted small mt-3">Review the warnings above before confirming. Locking does not declare hospital data complete.</p>
          <div className="review-dialog-actions"><button type="button" className="btn btn-secondary" onClick={stay} autoFocus>Keep reviewing</button><button type="button" className="btn btn-teal" onClick={() => void lock()} disabled={controlsDisabled || dirty || left > 0}>Confirm finalize & lock</button></div>
        </> : <>
          <p>{confirmation === "approve_all_remaining" ? "Approve all remaining draft fields across every visit, not just the current filter. Flagged and rejected fields will not be approved by this action." : confirmation === "guesses" ? "Accept library suggestions and guessed ranges across every visit. Guessed ranges are plausibility limits, not protocol-defined clinical ranges." : "Accept library suggestions across every visit, not just the current filter. These values are not stated in the protocol."}</p>
          <p className="muted small mt-3">This explicitly records approvals and saves your applied edits. Ordinary Save draft does not approve remaining fields.</p>
          <div className="review-dialog-actions"><button type="button" className="btn btn-secondary" onClick={stay} autoFocus>Keep reviewing</button><button type="button" className="btn btn-teal" disabled={controlsDisabled || editorOpen} onClick={async () => { if (await save(confirmation === "approve_all_remaining" ? "approve_all_remaining" : "approve_suggested", confirmation === "guesses")) setConfirmation(null); }}>{saving ? "Saving…" : "Confirm approval & save"}</button></div>
        </>}
        {error && <p className="error mt-3" role="alert">{error}</p>}
      </ReviewDialog>}

      {section && (
        <aside className="side-panel" aria-label="Protocol section">
          <div className="row row-between mb-3">
            <div className="section-title" style={{ marginBottom: 0 }}>
              {section.data
                ? (section.data.number === section.data.title || !/^[\d.]+$/.test(section.data.number)
                    ? section.data.title
                    : `§${section.data.number} ${section.data.title}`)
                : "Section"}
            </div>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSection(null)}>Close</button>
          </div>
          {section.loading && <p className="muted small">Loading…</p>}
          {section.error && <p className="error">{section.error}</p>}
          {section.data && (
            <>
              <div className="mono xs muted mb-3">
                {section.data.page ? `page ${section.data.page}` : ""}
                {section.data.located_by === "text" && (section.data.page ? " · " : "") + "passage found by searching the protocol text for this phrase"}
                {section.data.located_by === "title" && (section.data.page ? " · " : "") + "matched by heading"}
              </div>
              <div className="section-body">
                {formatSection(section.data.text).map((b, i) =>
                  b.kind === "h" ? <h4 key={i}>{b.text}</h4>
                  : b.kind === "li" ? <li key={i}>{b.text}</li>
                  : <p key={i}>{b.text}</p>)}
              </div>
            </>
          )}
        </aside>
      )}
    </div>
  );
}
