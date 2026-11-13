import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { api } from "../api/client";
import type { DashboardResponse, PageStatus, PageStatusNumbers, Queries360, SapResponse, StatResult, StatValue, Traceability } from "../api/types";
import Badge from "../components/Badge";
import { ResultForm, TraceabilityMatrix } from "../components/ResultsPanel";
import Stat from "../components/Stat";
import BarChart from "../components/charts/BarChart";
import DonutChart from "../components/charts/DonutChart";
import LineChart from "../components/charts/LineChart";

type Tab = "queries" | "pages" | "results";
const TABS: { key: Tab; label: string; needs?: string }[] = [
  { key: "queries", label: "Queries 360" },
  { key: "pages", label: "Page status", needs: "dashboard.subject_level" },
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
        {!can("dashboard.subject_level") && <div className="muted small">Queries about the form only. Page status is for the people who work with subjects' data.</div>}
      </div>
      <div className="tabs" role="tablist">
        {TABS.filter((t) => !t.needs || can(t.needs)).map((t) => (
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

/* One row per category, registry and verifier side by side. */
function FrequencyTable({ st }: { st: StatResult }) {
  type Side = { n: number; missing: number; categories: Record<string, { count: number; percent: number }> } | null;
  const app = st.app as unknown as Side;
  const ind = st.independent as unknown as Side;
  const names = Array.from(new Set([...Object.keys(app?.categories ?? {}), ...Object.keys(ind?.categories ?? {})])).sort();
  const cell = (side: Side, name: string) => {
    const c = side?.categories[name];
    return c ? `${c.count} (${c.percent.toFixed(1)}%)` : "not available";
  };
  return (
    <table className="table">
      <thead><tr><th>Category</th><th className="num">Registry</th><th className="num">Verifier</th></tr></thead>
      <tbody>
        {names.map((name) => <tr key={name}><td>{name}</td><td className="num">{cell(app, name)}</td><td className="num">{cell(ind, name)}</td></tr>)}
        <tr><td>n</td><td className="num">{app?.n ?? "not available"}</td><td className="num">{ind?.n ?? "not available"}</td></tr>
        <tr><td>Missing, not in the percents</td><td className="num">{app?.missing ?? "not available"}</td><td className="num">{ind?.missing ?? "not available"}</td></tr>
      </tbody>
    </table>
  );
}

function ResultsTab({ id }: { id: number }) {
  const { me, can } = useAuth();
  const [d, setD] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  // The rows behind the cards, for Add result and Edit, and the matrix when open.
  const [plan, setPlan] = useState<SapResponse | null>(null);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [matrix, setMatrix] = useState<Traceability | null>(null);
  const manage = can("sap.edit");

  const load = useCallback(async () => {
    try {
      const [dash, rows] = await Promise.all([api.dashboard(id), api.sap(id).catch(() => null)]);
      setD(dash);
      setPlan(rows);
      setError(null);
    } catch (e) { setError((e as Error).message); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const saved = async () => {
    setEditing(null);
    setMatrix(null);
    await load();
  };
  const remove = async (itemId: number, label: string) => {
    if (!window.confirm(`Delete the result "${label}"?`)) return;
    try { await api.sapDelete(id, itemId); await saved(); }
    catch (e) { setError((e as Error).message); }
  };
  const openMatrix = async () => {
    try { setMatrix(await api.traceability(id)); setEditing(null); }
    catch (e) { setError((e as Error).message); }
  };

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

      {plan && (
        <div className="row row-wrap mt-4">
          {manage && editing === null && <button type="button" className="btn btn-primary btn-sm" onClick={() => { setMatrix(null); setEditing("new"); }}>Add result</button>}
          <button type="button" className="btn btn-secondary btn-sm" onClick={openMatrix}>Traceability matrix</button>
        </div>
      )}
      {matrix && <TraceabilityMatrix id={id} m={matrix} onClose={() => setMatrix(null)} />}
      {plan && editing === "new" && <ResultForm id={id} plan={plan} onDone={saved} onCancel={() => setEditing(null)} />}

      {items.length === 0 && (
        <div className="card mt-4">
          <p className="strong">No results yet</p>
          <p className="muted small mt-2">
            {manage ? "Add a result: pick a field, the visits and a calculation." : "Results appear here once the data manager adds them."}
          </p>
        </div>
      )}
      {items.map((group) => {
        const row = plan?.items.find((x) => x.id === group[0].item_id);
        if (row && editing === row.id && plan) {
          return <ResultForm key={row.id} id={id} plan={plan} item={row} onDone={saved} onCancel={() => setEditing(null)} />;
        }
        return (
        <div className="card mt-4" key={group[0].item_id}>
          <div className="row row-between row-wrap">
            <p className="strong">{group[0].item_label}{row && row.endpoint_concept !== group[0].item_label && <span className="muted"> · {row.endpoint_concept}</span>}</p>
            <span className="row">
              <span className="pill">{group[0].item_kind}</span>
              {manage && row && editing === null && (
                <>
                  <button type="button" className="btn-link small" onClick={() => { setMatrix(null); setEditing(row.id); }}>Edit</button>
                  <button type="button" className="btn-link small" onClick={() => remove(row.id, row.label)}>Delete</button>
                </>
              )}
            </span>
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
                {rows.length === 0 && <p className="small">Not available: not enough approved data yet.</p>}
                {rows.length > 0 && st.name === "frequency" && <FrequencyTable st={st} />}
                {rows.length > 0 && st.name !== "frequency" && (
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
        );
      })}

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
