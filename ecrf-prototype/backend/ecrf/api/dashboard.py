"""Dashboard numbers. Every scalar statistic is returned alongside the
independently computed value and a pass/fail marker. A number that only
checks itself proves nothing."""

import math
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.config import config
from ecrf.schema import DraftECRF
from ecrf.stats import registry
from ecrf.storage import db
from ecrf.storage.models import (
    LIVE_QUERY,
    Observation,
    Organisation,
    Query,
    SapItem,
    Signoff,
    Subject,
    utcnow,
)

# The verification package deliberately lives outside ecrf/ and imports
# nothing from it. We import it here only to compare.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verification import expected_results as independent

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
TOLERANCE = 0.01
QUERY_STATUSES = ("open", "answered", "closed", "cancelled")


def _jsonable(v):
    """Replace NaN and infinity with None so the response can be serialised.

    A calculation can legitimately have nothing to work on. json.dumps refuses
    NaN, and a 500 reads as the app being broken rather than the statistic
    being unavailable."""
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and not math.isfinite(v))


def _leaves(v, path=()) -> dict:
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            out.update(_leaves(x, (*path, k)))
        return out
    return {path: v}


def _status(a, b) -> str:
    """Pass needs a number on both sides that agree. Two blanks agreeing with
    each other prove nothing, so a statistic that could not be computed is
    not available, never a pass."""
    if _missing(a) or _missing(b):
        return "not_available"
    x, y = _leaves(a), _leaves(b)
    if set(x) != set(y):
        return "fail"
    if any(_missing(x[k]) != _missing(y[k]) for k in x):
        return "fail"
    numbers = [k for k in x if not _missing(x[k])]
    if not numbers:
        return "not_available"
    try:
        return "pass" if all(abs(float(x[k]) - float(y[k])) < TOLERANCE for k in numbers) else "fail"
    except (TypeError, ValueError):
        return "fail"


def _results(s: Session, cu: CurrentUser, protocol_id: int, df) -> list[dict]:
    """One entry per SAP row and calculation, with the independent value beside
    the app's. Everything is limited to the caller's sites, on both sides."""
    v = db.locked_version(s, protocol_id)
    items = s.scalars(select(SapItem).where(SapItem.protocol_id == protocol_id).order_by(SapItem.id)).all()
    if v is None or not items:
        return []
    draft = DraftECRF.model_validate(v.content)
    subjects = len(s.scalars(scope.visible_subjects(cu, protocol_id)).all())
    sites = None if cu.site_ids is None else sorted(cu.site_ids)
    out = []
    for item in items:
        analysis = registry.resolve(item, draft, subjects)
        names = registry.applicable(item.kind, item.responder_rule, analysis.field_type if analysis else None)
        ours = {name: registry.run(name, df, analysis) for name in names} if analysis else {}
        theirs = independent.item_results(config.database_url, protocol_id, item.id, sites)
        for name in names:
            app, ind = ours.get(name), theirs.get(name)
            status = _status(app, ind)
            out.append({"item_id": item.id, "item_label": item.label, "item_kind": item.kind, "unit": item.unit,
                        "baseline": item.baseline_visit_id, "analysis": item.analysis_visit_id, "method": item.method,
                        "name": name, "label": registry.CALCULATIONS[name]["label"], "app": _jsonable(app),
                        "independent": _jsonable(ind), "status": status, "pass": status == "pass"})
    return out


@router.get("/calculations")
def calculations(cu: CurrentUser = Depends(require("dashboard.view"))):
    return registry.available()


@router.get("/{protocol_id}")
def dashboard(protocol_id: int, cu: CurrentUser = Depends(require("dashboard.view")),
              s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)

    # --- extraction summary from the latest version (real data) ---
    v = db.latest_version(s, protocol_id)
    extraction = None
    if v:
        draft = DraftECRF.model_validate(v.content)
        per_visit = [{"visit": f.visit, "fields": len(f.fields),
                      "flagged": sum(1 for x in f.fields if x.issue != "none"),
                      "approved": sum(1 for x in f.fields if x.status == "approved")}
                     for f in draft.forms]
        extraction = {"version": v.version, "summary": draft.summary,
                      "per_visit": per_visit, "rejections": len(draft.rejections),
                      "backend": draft.backend, "model": draft.model}

    # --- statistics over approved data, in the caller's scope ---
    df = registry.load_frame(s, protocol_id, cu.site_ids)
    visible = s.scalars(scope.visible_observations(cu, protocol_id)).all()
    return {"protocol": {"id": p.id, "name": p.name}, "extraction": extraction,
            "data": {"subjects": int(df.subject_id.nunique()), "readings": len(df), "entered_total": len(visible)},
            "stats": _results(s, cu, protocol_id, df)}


# ------------------------------------------------------------- Queries 360

def _monday(d) -> date:
    return d - timedelta(days=d.weekday())


def _as_of(q: Query, end: datetime) -> str | None:
    """Where this query stood at a moment. None if not raised yet, or cancelled."""
    if q.raised_at > end or (q.cancelled_at and q.cancelled_at <= end):
        return None
    if q.closed_at and q.closed_at <= end:
        return "closed"
    if q.answered_at and q.answered_at <= end:
        return "answered"
    return "open"


@router.get("/{protocol_id}/queries")
def queries_360(protocol_id: int, site: str | None = None, raised_by: str | None = None,
                cu: CurrentUser = Depends(require("dashboard.view")), s: Session = Depends(db.get_session)):
    """Counts by status, where things stood at the end of each week, and by
    site. raised_by is person or system. Someone who works on the form and not
    on subjects, the builder, sees only queries about the study as a whole."""
    scope.protocol_or_404(s, cu, protocol_id)
    q = select(Query).where(Query.protocol_id == protocol_id)
    if not cu.can("dashboard.subject_level"):
        q = q.where(Query.observation_id.is_(None), Query.subject_ref.is_(None))
    if cu.site_ids is not None:
        q = q.where(Query.site_org_id.in_(cu.site_ids))
    rows = list(s.scalars(q))
    orgs = {o.id: o for o in s.scalars(select(Organisation).where(
        Organisation.id.in_({r.site_org_id for r in rows if r.site_org_id})))}
    sites = sorted({orgs[r.site_org_id].code for r in rows if r.site_org_id in orgs})
    if site:
        rows = [r for r in rows if r.site_org_id in orgs and orgs[r.site_org_id].code == site]
    if raised_by:
        rows = [r for r in rows if (r.raised_by == "system") == (raised_by == "system")]

    empty = dict.fromkeys(QUERY_STATUSES, 0)
    counts = dict(empty)
    by_site: dict[str, dict] = {}
    for r in rows:
        counts[r.status] += 1
        code = orgs[r.site_org_id].code if r.site_org_id in orgs else "no site"
        by_site.setdefault(code, {"site": code, **empty})[r.status] += 1

    weeks = []
    if rows:
        monday, last = _monday(min(r.raised_at for r in rows).date()), _monday(utcnow().date())
        while monday <= last:
            end = datetime.combine(monday + timedelta(days=6), time.max)
            week = {"week": monday.isoformat(), "open": 0, "answered": 0, "closed": 0}
            for r in rows:
                state = _as_of(r, end)
                if state:
                    week[state] += 1
            weeks.append(week)
            monday += timedelta(days=7)
    return {"counts": counts, "weeks": weeks, "by_site": [by_site[k] for k in sorted(by_site)], "sites": sites}


# ------------------------------------------------------------- Page status

_STATE_ORDER = ("draft", "submitted", "monitor_reviewed", "approved")


@router.get("/{protocol_id}/page-status")
def page_status(protocol_id: int, cu: CurrentUser = Depends(require("dashboard.subject_level")),
                s: Session = Depends(db.get_session)):
    """Per site, then per subject. A visit counts once, at its least advanced
    value. A signed visit counts as approved and as signed. There is no overdue
    column, because there are no visit windows to measure it against."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    v = db.locked_version(s, protocol_id)
    if v is None:
        return {"locked": False, "visits": 0, "sites": []}
    visits = list(dict.fromkeys(f.visit for f in DraftECRF.model_validate(v.content).forms))
    subjects = list(s.scalars(scope.visible_subjects(cu, protocol_id).order_by(Subject.code)))
    refs = [x.id for x in subjects]
    states: dict[tuple[int, str], str] = {}
    rows = s.execute(select(Observation.subject_ref, Observation.visit, Observation.status).where(
        Observation.protocol_id == protocol_id, Observation.subject_ref.in_(refs))).all()
    for ref, visit, status in rows:
        now = states.get((ref, visit))
        if now is None or _STATE_ORDER.index(status) < _STATE_ORDER.index(now):
            states[(ref, visit)] = status
    signed = {(x.subject_ref, x.visit) for x in s.scalars(select(Signoff).where(
        Signoff.protocol_id == protocol_id, Signoff.invalidated_at.is_(None)))}
    live: dict[int, int] = {}
    for ref in s.scalars(select(Query.subject_ref).where(Query.protocol_id == protocol_id, Query.status.in_(LIVE_QUERY))):
        live[ref] = live.get(ref, 0) + 1

    numbers = ("expected", "not_started", "draft", "submitted", "monitor_reviewed", "approved", "signed",
               "needs_review", "needs_approval", "needs_signoff", "open_queries")
    orgs = {o.id: o for o in s.scalars(select(Organisation).where(
        Organisation.id.in_({x.site_org_id for x in subjects})))}
    sites: dict[int, dict] = {}
    for subj in subjects:
        row = {"id": subj.id, "code": subj.code, **dict.fromkeys(numbers, 0)}
        row["expected"], row["open_queries"] = len(visits), live.get(subj.id, 0)
        for visit in visits:
            state = states.get((subj.id, visit))
            if state is None:
                row["not_started"] += 1
                continue
            row[state] += 1
            if state == "submitted" and p.monitor_review_required:
                row["needs_review"] += 1
            elif state in ("submitted", "monitor_reviewed"):
                row["needs_approval"] += 1
            elif state == "approved":
                if (subj.id, visit) in signed:
                    row["signed"] += 1
                elif p.investigator_signature_required:
                    row["needs_signoff"] += 1
        org = orgs.get(subj.site_org_id)
        group = sites.setdefault(subj.site_org_id, {"site": org.code if org else "", "site_name": org.name if org else "",
                                                    **dict.fromkeys(numbers, 0), "subjects": []})
        group["subjects"].append(row)
        for key in numbers:
            group[key] += row[key]
    return {"locked": True, "visits": len(visits), "sites": [sites[k] for k in sorted(sites, key=lambda i: sites[i]["site"])]}


@router.post("/{protocol_id}/unsupported")
def unsupported(protocol_id: int, name: str, cu: CurrentUser = Depends(require("sap.edit")),
                s: Session = Depends(db.get_session)):
    """Exists only to demonstrate the refusal. Anything not in the registry
    is refused, never approximated. A registered name is not what this route
    is for, so it is a bad request rather than a pretend answer."""
    scope.protocol_or_404(s, cu, protocol_id)
    if name in registry.CALCULATIONS:
        raise HTTPException(400, f"'{name}' is an approved calculation; read it from the dashboard.")
    raise HTTPException(
        403, f"'{name}' is not an approved calculation. The approved set is: "
             f"{', '.join(registry.CALCULATIONS)}. Adding one means writing, testing "
             f"and independently verifying it first.")
