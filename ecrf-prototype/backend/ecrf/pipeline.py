"""End to end orchestration for stages 1 to 3.

    ingest  ->  pass one (visits, or visits + forms)
            ->  pass two (per visit, or per form)  ->  verify quotes
            ->  CDASH enrich ->  save version

Pass one is sent alone first so it writes the provider's prompt cache; the
pass-two calls then hit it. The two passes are separate functions so a
person can correct the visit list between them, which is where most of the
cost and most of the instability live.
"""

import logging
import time

from ecrf import cdash, sections, verify
from ecrf.config import config
from ecrf.extract import get_extractor
from ecrf.extract.base import Extractor, Usage
from ecrf.ingest import Document, load
from ecrf.schema import DraftECRF, ExtractionPlan, FieldDef, Rejection, VisitForm

log = logging.getLogger("ecrf.pipeline")


def _context_for(doc: Document, key: str) -> str:
    mode = config.context_mode
    if mode == "sections":
        return sections.select(doc, key)
    if mode == "full":
        return doc.text
    # auto
    if doc.tokens_estimate > config.context_token_limit:
        return sections.select(doc, key)
    return doc.text


def _strategy(strategy: str | None) -> str:
    s = strategy or config.extract_strategy
    if s not in ("per_visit", "per_form"):
        raise ValueError(f"unknown EXTRACT_STRATEGY: {s}")
    return s


def plan(doc: Document, ex: Extractor, strategy: str | None = None) -> ExtractionPlan:
    """Pass one only. Full text, this is the backbone."""
    strategy = _strategy(strategy)
    log.info("[pipeline] pass one backend=%s model=%s tokens~%s strategy=%s",
             ex.name, ex.model, doc.tokens_estimate, strategy)
    if strategy == "per_form":
        p = ex.plan(doc.text)
    else:
        p = ExtractionPlan(visits=ex.list_visits(doc.text).visits, forms=[])
    log.info("[pipeline] visits: %s forms: %s", p.visits, [f.name for f in p.forms])
    return p


def estimated_calls(p: ExtractionPlan, strategy: str | None = None) -> int:
    return len(p.forms) if _strategy(strategy) == "per_form" and p.forms else len(p.visits)


def run_fields(doc: Document, p: ExtractionPlan, ex: Extractor, protocol_id: int,
               strategy: str | None = None, pass_one_usage: Usage | None = None,
               t0: float | None = None) -> DraftECRF:
    """Pass two on a confirmed plan, then verification and enrichment."""
    strategy = _strategy(strategy)
    t0 = t0 or time.time()
    threshold = config.quote_match_threshold
    rejections: list[Rejection] = []
    by_visit: dict[str, list[FieldDef]] = {v: [] for v in p.visits}
    form_names: dict[str, list[str]] = {v: [] for v in p.visits}

    if strategy == "per_form" and p.forms:
        for form in p.forms:
            ctx = _context_for(doc, form.name)
            ff = ex.fields_for_form(ctx, form.name, form.visits, p.visits)
            kept, rej = verify.filter_fields(form.name, ff.fields, doc, threshold)
            kept = [cdash.enrich(f) for f in kept]
            rejections.extend(rej)
            for v in form.visits:
                if v not in by_visit:
                    continue
                form_names[v].append(form.name)
                have = {f.name for f in by_visit[v]}
                by_visit[v].extend(f.model_copy(deep=True) for f in kept if f.name not in have)
            log.info("[pipeline] form %s: kept %s, rejected %s, at %s visits",
                     form.name, len(kept), len(rej), len(form.visits))
    else:
        for v in p.visits:
            ctx = _context_for(doc, v)
            form = ex.fields_for_visit(ctx, v, p.visits)
            kept, rej = verify.filter_fields(v, form.fields, doc, threshold)
            by_visit[v] = [cdash.enrich(f) for f in kept]
            form_names[v] = [form.form]
            rejections.extend(rej)
            log.info("[pipeline] %s: kept %s, rejected %s", v, len(kept), len(rej))

    forms = [VisitForm(visit=v, form="; ".join(form_names[v]) or "Assessments", fields=by_visit[v])
             for v in p.visits]
    counts = {"exact": 0, "approximate": 0, "rejected": len(rejections), "flagged": 0}
    for f in forms:
        for fld in f.fields:
            counts[fld.verdict] += 1
            if fld.issue != "none":
                counts["flagged"] += 1
    total = sum(len(f.fields) for f in forms) + len(rejections)

    usage = Usage()
    if pass_one_usage:
        usage.add(pass_one_usage)
    usage.add(ex.usage)
    summary = {
        "visits": len(p.visits),
        "fields_generated": total,
        "fields_kept": total - len(rejections),
        **counts,
        "threshold": threshold,
        "seconds": round(time.time() - t0, 2),
        "strategy": strategy,
        "forms": len(p.forms),
        **usage.summary(),
    }
    log.info("[pipeline] done: %s", summary)
    return DraftECRF(protocol_id=protocol_id, protocol_hash=doc.hash, version=1,
                     backend=ex.name, model=ex.model, forms=forms, rejections=rejections,
                     summary=summary)


def run(pdf_path: str, protocol_id: int, backend: str | None = None,
        doc: Document | None = None, force: bool = False,
        strategy: str | None = None) -> DraftECRF:
    """Both passes with no human step in between. Used by the tests and
    the mock; the API's two-step route is what a person uses."""
    t0 = time.time()
    doc = doc or load(pdf_path)
    ex = get_extractor(backend)
    ex.begin_run(doc.hash, force=force)
    p = plan(doc, ex, strategy)
    pass_one = Usage()
    pass_one.add(ex.usage)
    ex.begin_run(doc.hash, force=force)
    return run_fields(doc, p, ex, protocol_id, strategy, pass_one_usage=pass_one, t0=t0)
