import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { api } from "../api/client";
import type { DashboardResponse, PageStatus, PageStatusNumbers, Queries360, StatResult, StatValue } from "../api/types";
import Badge from "../components/Badge";
import Stat from "../components/Stat";
import BarChart from "../components/charts/BarChart";
import DonutChart from "../components/charts/DonutChart";
import LineChart from "../components/charts/LineChart";

type Tab = "queries" | "pages" | "results";
const TABS: { key: Tab; label: string }[] = [
  { key: "queries", label: "Queries 360" },
  { key: "pages", label: "Page status" },
  { key: "results", label: "Results" },
];

export default function Dashboard() {
  const id = Number(useParams().id);
  const { me, can } = useAuth();
  const [tab, setTab] = useState<Tab>("queries");
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");

  useEffect(() => {
    api.dashboard(id).then((d) => setName(d.protocol.name)).catch((e) => setError((e as Error).message));
  }, [id]);

  const blank = async () => {
    setError(null);
    try { await api.blankPdf(id); } catch (e) { setError((e as Error).message); }
  };

  return (
    <div className="page">
      <div className="page-head">
        <div className="row row-between row-wrap">
          <h1 className="page-title">{name || "Dashboard"}</h1>
          {can("report.pdf") && <button type="button" className="btn btn-secondary btn-sm" onClick={blank}>Blank eCRF PDF</button>}
        </div>
        {me?.org.type === "site" && <div className="muted small">Your site's numbers only.</div>}
      </div>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button type="button" role="tab" aria-selected={tab === t.key} key={t.key}
                  className={`tab${tab === t.key ? " active" : ""}`} onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
      </div>
      {tab === "queries" && <QueriesTab id={id} />}
      {tab === "pages" && <PagesTab id={id} />}
      {tab === "results" && <ResultsTab id={id} />}
      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}

/* ---------------------------------------------------------- Queries 360 */

function QueriesTab({ id }: { id: number }) {
  const [site, setSite] = useState("");
  const [raisedBy, setRaisedBy] = useState("");
  const [d, setD] = useState<Queries360 | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.queries360(id, { site, raised_by: raisedBy }).then((x) => { setD(x); setError(null); })
      .catch((e) => setError((e as Error).message));
  }, [id, site, raisedBy]);

  if (error) return <p className="error">{error}</p>;
  if (!d) return <p className="muted">Loading…</p>;
  return (
    <>
      <div className="row row-wrap filters mb-3">
        <select className="input" value={site} onChange={(e) => setSite(e.target.value)} aria-label="Site">
          <option value="">All sites</option>
          {d.sites.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <select className="input" value={raisedBy} onChange={(e) => setRaisedBy(e.target.value)} aria-label="Raised by">
          <option value="">Raised by anyone</option>
          <option value="person">A person</option>
          <option value="system">An edit check</option>
        </select>
      </div>
      <div className="grid-4">
        <Stat label="Open" value={d.counts.open} sub="waiting for an answer" />
        <Stat label="Answered" value={d.counts.answered} sub="waiting to be closed" />
        <Stat label="Closed" value={d.counts.closed} sub="settled" />
        <Stat label="Cancelled" value={d.counts.cancelled} sub="withdrawn" />
      </div>
      <div className="card mt-4">
        <div className="section-title">Where queries stood at the end of each week</div>
        {d.weeks.length === 0
          ? <p className="muted small">No queries yet.</p>
          : <LineChart labels={d.weeks.map((w) => w.week)} series={[
              { label: "Open", color: "var(--rust)", values: d.weeks.map((w) => w.open) },
              { label: "Answered", color: "var(--amber)", values: d.weeks.map((w) => w.answered) },
              { label: "Closed", color: "var(--teal)", values: d.weeks.map((w) => w.closed) },
            ]} />}
      </div>
      <div className="card mt-4">
        <div className="section-title">By site</div>
        <table className="table">
          <thead><tr><th>Site</th><th className="num">Open</th><th className="num">Answered</th><th className="num">Closed</th><th className="num">Cancelled</th></tr></thead>
          <tbody>
            {d.by_site.map((r) => (
              <tr key={r.site}><td>{r.site}</td><td className="num">{r.open}</td><td className="num">{r.answered}</td><td className="num">{r.closed}</td><td className="num">{r.cancelled}</td></tr>
            ))}
            {d.by_site.length === 0 && <tr><td colSpan={5} className="muted small">No queries yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}

/* ---------------------------------------------------------- Page status */

const COLUMNS: { key: keyof PageStatusNumbers; label: string }[] = [
  { key: "expected", label: "Expected" }, { key: "not_started", label: "Not started" }, { key: "draft", label: "Draft" },
  { key: "submitted", label: "Submitted" }, { key: "monitor_reviewed", label: "Monitor reviewed" },
  { key: "approved", label: "Approved" }, { key: "signed", label: "Signed" },
  { key: "needs_review", label: "Needs review" }, { key: "needs_approval", label: "Needs approval" },
  { key: "needs_signoff", label: "Needs sign-off" }, { key: "open_queries", label: "Open queries" },
];
const ACTION = new Set<keyof PageStatusNumbers>(["needs_review", "needs_approval", "needs_signoff", "open_queries"]);

function Numbers({ row }: { row: PageStatusNumbers }) {
  return (
    <>
      {COLUMNS.map((c) => (
        <td key={c.key} className={`num${ACTION.has(c.key) && row[c.key] > 0 ? " needs-action" : ""}`}>{row[c.key]}</td>
      ))}
    </>
  );
}

function PagesTab({ id }: { id: number }) {
  const { me, can } = useAuth();
  const [d, setD] = useState<PageStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.pageStatus(id).then(setD).catch((e) => setError((e as Error).message));
  }, [id]);

  const to = (code: string) => {
    if (me?.org.type === "site") return `/site/s/${id}/patients/${encodeURIComponent(code)}`;
    return can("listing.view") ? `/sponsor/p/${id}/data?subject=${encodeURIComponent(code)}` : null;
  };
  const casebook = (subjectId: number, code: string) => {
    setError(null);
    api.casebookPdf(subjectId, code).catch((e) => setError((e as Error).message));
  };

  if (error) return <p className="error">{error}</p>;
  if (!d) return <p className="muted">Loading…</p>;
  if (!d.locked) return <div className="card"><p className="muted small">Page status starts once the form is locked.</p></div>;
  return (
    <div className="card">
      <p className="muted small mb-3">
        Expected is the {d.visits} visits on the locked form times the subjects. A visit counts once, at its least advanced
        value. There is no overdue column, because the system has no visit windows to measure it against.
      </p>
      <div className="table-scroll">
        <table className="table table-compact">
          <thead><tr><th>Site / subject</th>{COLUMNS.map((c) => <th key={c.key} className="num">{c.label}</th>)}<th /></tr></thead>
          <tbody>
            {d.sites.map((site) => [
              <tr className="group-row" key={site.site}><td>{site.site} · {site.site_name}</td><Numbers row={site} /><td /></tr>,
              ...site.subjects.map((r) => {
                const link = to(r.code);
                return (
                  <tr className="sub-row" key={r.id}>
                    <td className="mono">{link ? <Link className="inline" to={link}>{r.code}</Link> : r.code}</td>
                    <Numbers row={r} />
                    <td className="num">{can("listing.view") && <button type="button" className="btn-link small" onClick={() => casebook(r.id, r.code)}>Casebook</button>}</td>
                  </tr>
                );
              }),
            ])}
            {d.sites.length === 0 && <tr><td colSpan={COLUMNS.length + 2} className="muted small">No subjects yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- Results */

const NAMES: Record<string, string> = {
  n: "n", mean: "Mean", sd: "SD", median: "Median", min: "Min", max: "Max", ci_low: "95% CI low", ci_high: "95% CI high",
  t: "t", p: "p (paired t-test)", responders: "Responders", rate: "Rate", subjects: "Subjects", denominator: "Out of",
  percent: "Percent", expected: "Expected slots", present: "Filled slots",
};
const WHOLE = new Set(["n", "responders", "subjects", "denominator", "expected", "present"]);

function show(key: string, v: StatValue | undefined): string {
  if (v === null || v === undefined || typeof v === "object") return "not available";
  if (WHOLE.has(key)) return String(v);
  if (key === "p" && v < 0.0001) return "< 0.0001";
  return v.toFixed(key === "p" ? 4 : key === "rate" || key === "ci_low" || key === "ci_high" ? 3 : 2);
}

/* Every number in a result, in order, with a readable label. */
function lines(st: StatResult): { path: string[]; label: string }[] {
  const shape = (st.app ?? st.independent) as Record<string, StatValue> | null;
  if (!shape) return [];
  const out: { path: string[]; label: string }[] = [];
  for (const [k, v] of Object.entries(shape)) {
    if (v !== null && typeof v === "object") {
      const visit = k === "baseline" ? st.baseline : st.analysis;
      for (const inner of Object.keys(v)) out.push({ path: [k, inner], label: `${visit ?? k}: ${NAMES[inner] ?? inner}` });
    } else {
      out.push({ path: [k], label: NAMES[k] ?? k });
    }
  }
  return out;
}

function pick(v: StatResult["app"], path: string[]): StatValue | undefined {
  let at: unknown = v;
  for (const p of path) at = at === null || at === undefined ? undefined : (at as Record<string, unknown>)[p];
  return at as StatValue | undefined;
}

function ResultsTab({ id }: { id: number }) {
  const { me, can } = useAuth();
  const [d, setD] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);

  const load = useCallback(async () => {
    try { setD(await api.dashboard(id)); setError(null); }
    catch (e) { setError((e as Error).message); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const seed = async () => {
    setSeeding(true);
    try { await api.seed(id); await load(); }
    catch (e) { setError((e as Error).message); }
    finally { setSeeding(false); }
  };

  const items = useMemo(() => {
    const m = new Map<number, StatResult[]>();
    for (const st of d?.stats ?? []) m.set(st.item_id, [...(m.get(st.item_id) ?? []), st]);
    return Array.from(m.values());
  }, [d]);

  if (error) return <p className="error">{error}</p>;
  if (!d) return <p className="muted">Loading…</p>;
  const sponsor = me?.org.type === "sponsor";
  const ex = d.extraction;
  const sum = ex?.summary;

  return (
    <>
      <div className="grid-2">
        <Stat label="Subjects" value={d.data.subjects} sub="with an approved value" />
        <Stat label="Approved values" value={d.data.readings.toLocaleString()} sub={`of ${d.data.entered_total.toLocaleString()} you can see`} />
      </div>

      {items.length === 0 && (
        <div className="card mt-4">
          <p className="strong">No results yet</p>
          <p className="muted small mt-2">
            Results come from the rows of the statistical analysis plan.
            {sponsor && <> <Link className="inline" to={`/sponsor/p/${id}/sap`}>Open the plan</Link>.</>}
          </p>
        </div>
      )}
      {items.map((group) => (
        <div className="card mt-4" key={group[0].item_id}>
          <div className="row row-between row-wrap">
            <p className="strong">{group[0].item_label}</p>
            <span className="pill">{group[0].item_kind}</span>
          </div>
          <p className="muted small">
            {[group[0].baseline && `Baseline ${group[0].baseline}`, group[0].analysis && `Analysis ${group[0].analysis}`, group[0].unit, group[0].method].filter(Boolean).join(" · ")}
          </p>
          {group.map((st) => {
            const rows = lines(st);
            return (
              <div className={`mt-3${st.status === "not_available" ? " na" : ""}`} key={st.name}>
                <div className="row row-between">
                  <span className="section-title">{st.label}</span>
                  <Badge kind={st.status} />
                </div>
                {rows.length === 0
                  ? <p className="small">Not available: not enough approved data yet.</p>
                  : (
                    <table className="table">
                      <thead><tr><th>Statistic</th><th className="num">Registry</th><th className="num">Verifier</th></tr></thead>
                      <tbody>
                        {rows.map((r) => (
                          <tr key={r.path.join(".")}>
                            <td>{r.label}</td>
                            <td className="num">{show(r.path[r.path.length - 1], pick(st.app, r.path))}</td>
                            <td className="num">{show(r.path[r.path.length - 1], pick(st.independent, r.path))}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
              </div>
            );
          })}
        </div>
      ))}

      {sponsor && can("data.approve") && d.data.entered_total === 0 && ex && (
        <div className="card mt-4">
          <p className="muted small mb-3">No data entered yet. Synthetic subjects let you try the numbers; they still need approving.</p>
          <button type="button" className="btn btn-secondary btn-sm" onClick={seed} disabled={seeding}>{seeding ? "Seeding…" : "Seed 20 synthetic subjects"}</button>
        </div>
      )}

      {sponsor && ex && sum && (
        <div className="grid-2 mt-4">
          <div className="card" style={{ marginTop: 0 }}>
            <div className="section-title">How the form was verified</div>
            <DonutChart
              slices={[
                { label: "exact", value: sum.exact, color: "var(--teal)" },
                { label: "approximate", value: sum.approximate, color: "var(--amber)" },
                { label: "rejected", value: sum.rejected, color: "var(--rust)" },
              ]}
              centerLabel={String(sum.fields_generated)}
            />
            <p className="muted small mt-3">{sum.fields_kept} of {sum.fields_generated} generated fields kept. {sum.rejected} deleted before review.</p>
          </div>
          <div className="card" style={{ marginTop: 0 }}>
            <div className="section-title">Fields per visit</div>
            <BarChart data={ex.per_visit.map((v) => ({ label: v.visit, value: v.fields }))} />
          </div>
        </div>
      )}
    </>
  );
}
