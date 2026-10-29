import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { DraftResponse, FieldChange, FieldDef, VersionRow } from "../api/types";
import FieldCard from "../components/FieldCard";
import Stat from "../components/Stat";
import { useAuth } from "../auth/useAuth";

type SectionView = { number: string; title: string; page: number; text: string };

const key = (visit: string, name: string) => `${visit}\u0000${name}`;

export default function Review() {
  const id = Number(useParams().id);
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

  const load = useCallback(async () => {
    try {
      const r = await api.draft(id);
      setResp(r);
      setError(null);
      setActive((a) => (a && r.draft?.forms.some((f) => f.visit === a) ? a : r.draft?.forms[0]?.visit ?? null));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const loadVersions = async () => {
    try { setVersions(await api.versions(id)); }
    catch (e) { setError((e as Error).message); }
  };

  const onChange = (visit: string, name: string, change: Partial<FieldChange>) => {
    setChanges((prev) => {
      const k = key(visit, name);
      return { ...prev, [k]: { ...(prev[k] ?? { visit, name }), ...change } };
    });
  };

  const save = async (action: "save" | "approve_all_remaining" | "approve_suggested", includeGuesses = false) => {
    setSaving(true); setError(null);
    try {
      await api.review(id, Object.values(changes), note.trim() || undefined, action, includeGuesses);
      setChanges({});
      setNote("");
      await load();
      if (versions) await loadVersions();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const lock = async () => {
    setLocking(true); setError(null);
    try { await api.lock(id); await load(); if (versions) await loadVersions(); }
    catch (e) { setError((e as Error).message); }
    finally { setLocking(false); }
  };

  const showSection = async (n: string) => {
    setSection({ loading: true, data: null, error: null });
    try { setSection({ loading: false, data: await api.section(id, n), error: null }); }
    catch (e) { setSection({ loading: false, data: null, error: (e as Error).message }); }
  };

  const draft = resp?.draft ?? null;
  const form = useMemo(() => draft?.forms.find((f) => f.visit === active) ?? null, [draft, active]);
  const pending = Object.keys(changes).length;

  // Merge pending local edits into the field so the card reflects them.
  const merged = (f: FieldDef, visit: string): FieldDef => {
    const c = changes[key(visit, f.name)];
    if (!c) return f;
    return {
      ...f,
      status: c.status ?? f.status,
      min: c.min !== undefined ? c.min : f.min,
      max: c.max !== undefined ? c.max : f.max,
      required: c.required ?? f.required,
      repeats: c.repeats ?? f.repeats,
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
  const visible = form ? form.fields.map((f) => merged(f, form.visit)).filter(matches) : [];
  const countBy = (pred: (f: FieldDef) => boolean) => (form ? form.fields.map((f) => merged(f, form.visit)).filter(pred).length : 0);
  const blockers = resp.lock_blockers ?? { draft: 0, flagged: 0 };
  const left = blockers.draft + blockers.flagged;

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">{resp.protocol.name}</h1>
        <div className="row row-wrap row-between">
          <div className="mono small muted">
            v{resp.version} · {draft.backend} · {draft.model} · hash {resp.protocol.hash} · threshold {s.threshold}
            {s.est_cost_usd !== undefined && (
              <> · {s.llm_calls_made} call{s.llm_calls_made === 1 ? "" : "s"}{s.llm_calls_from_cache ? ` + ${s.llm_calls_from_cache} cached` : ""} · ${s.est_cost_usd.toFixed(4)}{s.strategy ? ` · ${s.strategy}` : ""}</>
            )}
          </div>
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
                type="button" className="btn btn-teal btn-sm" onClick={lock}
                disabled={locking || left > 0 || pending > 0}
                title={pending > 0 ? "Save your pending changes first" : left > 0 ? "Every field must be approved or rejected first" : "Freeze this version for sites"}
              >
                {locking ? "Locking…" : "Lock form"}
              </button>
            </div>
          )}
        </div>
      </div>

      {locked && (
        <div className="lock-banner">
          <span className="strong">Locked</span>
          <span>by {resp.locked_by}{resp.locked_at && <> on {new Date(resp.locked_at).toLocaleString()}</>}. This version is frozen; sites enter data against it and nothing here can change.</span>
        </div>
      )}

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

      <div className="mt-5">
        <div className="tabs" role="tablist">
          {draft.forms.map((f) => (
            <button
              key={f.visit}
              type="button"
              role="tab"
              aria-selected={f.visit === active}
              className={`tab${f.visit === active ? " active" : ""}`}
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
              <div className="filter-bar">
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
              </div>
            )}
            {form.fields.length > 0 && visible.length === 0 && <p className="muted small">No fields match the filter.</p>}
            {visible.map((f) => (
              <FieldCard
                key={`${form.visit}-${f.name}`}
                field={f}
                onChange={(c) => onChange(form.visit, f.name, c)}
                onShowSection={showSection}
                readOnly={locked}
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

      {error && <p className="error mt-3">{error}</p>}

      {can("form.edit") && !locked && <div className="sticky-bar">
        <span className="small muted">
          <span className="mono">{pending}</span> pending change{pending === 1 ? "" : "s"}
        </span>
        <input
          className="input grow"
          placeholder="Review note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button type="button" className="btn btn-primary" onClick={() => save("save")} disabled={saving || pending === 0}>
          {saving ? "Saving…" : "Save review"}
        </button>
        {suggestedCount > 0 && (
          <button
            type="button" className="btn btn-secondary" onClick={() => save("approve_suggested")} disabled={saving}
            title="Flagged only because the protocol gave no unit, range or choices and the CDASH library has a standard one. Approving accepts the library's values."
          >
            Accept {suggestedCount} library suggestion{suggestedCount === 1 ? "" : "s"}
          </button>
        )}
        {guessedCount > 0 && (
          <button
            type="button" className="btn btn-secondary" onClick={() => save("approve_suggested", true)} disabled={saving}
            title="Also approves fields whose range was guessed from the unit or name. Look at them first: they are plausibility limits, not clinical ranges."
          >
            Accept {guessedCount} guessed range{guessedCount === 1 ? "" : "s"} too
          </button>
        )}
        <button type="button" className="btn btn-secondary" onClick={() => save("approve_all_remaining")} disabled={saving}>
          Approve all remaining
        </button>
      </div>}

      {section && (
        <aside className="side-panel" aria-label="Protocol section">
          <div className="row row-between mb-3">
            <div className="section-title" style={{ marginBottom: 0 }}>
              {section.data ? `§${section.data.number} ${section.data.title}` : "Section"}
            </div>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSection(null)}>Close</button>
          </div>
          {section.loading && <p className="muted small">Loading…</p>}
          {section.error && <p className="error">{section.error}</p>}
          {section.data && (
            <>
              <div className="mono xs muted mb-3">page {section.data.page}</div>
              <pre>{section.data.text}</pre>
            </>
          )}
        </aside>
      )}
    </div>
  );
}
