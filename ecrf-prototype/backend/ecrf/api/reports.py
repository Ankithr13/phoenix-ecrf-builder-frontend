"""The data listing and the PDFs."""

import csv
import io
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf import pdf
from ecrf.api.chain import valid_signoff
from ecrf.api.data import shown
from ecrf.api.sap import matrix
from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.schema import DraftECRF
from ecrf.storage import db
from ecrf.storage.models import (
    LIVE_QUERY,
    Observation,
    ObservationHistory,
    Organisation,
    Query,
    Signoff,
    Subject,
    UserAccessEvent,
    utcnow,
)

router = APIRouter(tags=["reports"])

ORDER = ("draft", "submitted", "monitor_reviewed", "approved")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def _locked(s: Session, protocol_id: int):
    v = db.locked_version(s, protocol_id)
    if v is None:
        raise HTTPException(409, "The form is not locked yet")
    return v, DraftECRF.model_validate(v.content)


# ------------------------------------------------------------------ listing

def _listing(s: Session, cu: CurrentUser, protocol_id: int, form: str) -> dict:
    scope.protocol_or_404(s, cu, protocol_id)
    _, draft = _locked(s, protocol_id)
    pages = [f for f in draft.forms if f.form == form]
    if not pages:
        raise HTTPException(404, "form not found")
    wanted = {(page.visit, f.name) for page in pages for f in page.fields}
    columns = list(dict.fromkeys(f.name for page in pages for f in page.fields))
    order = {page.visit: n for n, page in enumerate(pages)}
    codes = {x.id: x for x in s.scalars(scope.visible_subjects(cu, protocol_id))}
    sites = {o.id: o.code for o in s.scalars(select(Organisation).where(
        Organisation.id.in_({x.site_org_id for x in codes.values()})))}
    rows: dict[tuple, dict] = {}
    for o in s.scalars(scope.visible_observations(cu, protocol_id)):
        if (o.visit, o.field_name) not in wanted or o.subject_ref not in codes:
            continue
        subj = codes[o.subject_ref]
        row = rows.setdefault((subj.code, order[o.visit], o.repeat_num), {
            "subject": subj.code, "site": sites.get(subj.site_org_id), "visit": o.visit,
            "repeat": o.repeat_num, "status": o.status, "values": {}})
        row["values"][o.field_name] = shown(o)
        if ORDER.index(o.status) < ORDER.index(row["status"]):
            row["status"] = o.status
    return {"form": form, "columns": columns, "rows": [rows[k] for k in sorted(rows)]}


@router.get("/api/listing/{protocol_id}")
def listing_forms(protocol_id: int, cu: CurrentUser = Depends(require("listing.view")),
                  s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    _, draft = _locked(s, protocol_id)
    return {"forms": list(dict.fromkeys(f.form for f in draft.forms))}


@router.get("/api/listing/{protocol_id}/{form}")
def listing(protocol_id: int, form: str, cu: CurrentUser = Depends(require("listing.view")),
            s: Session = Depends(db.get_session)):
    return _listing(s, cu, protocol_id, form)


def _cell(value) -> str:
    """A spreadsheet runs a cell starting with one of these as a formula, and
    entered text should never be able to do that."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "@", "\t", "\r") or (text[:1] == "-" and not re.fullmatch(r"-[\d.]+", text)):
        return "'" + text
    return text


@router.get("/api/listing/{protocol_id}/{form}/export")
def listing_export(protocol_id: int, form: str, cu: CurrentUser = Depends(require("listing.export")),
                   s: Session = Depends(db.get_session)):
    """CSV of what the listing shows. Each export is written to the access log."""
    data = _listing(s, cu, protocol_id, form)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Subject", "Site", "Visit", "Repeat", "Status", *data["columns"]])
    for r in data["rows"]:
        w.writerow([_cell(x) for x in (r["subject"], r["site"], r["visit"], r["repeat"], r["status"],
                                       *(r["values"].get(c) for c in data["columns"]))])
    s.add(UserAccessEvent(user_id=cu.user.id, action="export", by=cu.user.email,
                          detail=f"listing: protocol {protocol_id}, form {form}, {len(data['rows'])} rows"))
    s.commit()
    return Response(out.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="listing_{protocol_id}_{_safe(form)}.csv"'})


# --------------------------------------------------------------------- PDFs

def _pdf(content: bytes, filename: str) -> Response:
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{_safe(filename)}.pdf"'})


@router.get("/api/protocols/{protocol_id}/pdf/blank")
def blank_pdf(protocol_id: int, cu: CurrentUser = Depends(require("report.pdf")),
              s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    v, draft = _locked(s, protocol_id)
    locked = v.locked_at.date().isoformat() if v.locked_at else "date not recorded"
    return _pdf(pdf.blank_ecrf(p.name, v.version, locked, draft), f"blank_ecrf_{protocol_id}_v{v.version}")


@router.get("/api/protocols/{protocol_id}/pdf/traceability")
def traceability_pdf(protocol_id: int, cu: CurrentUser = Depends(require("dashboard.view")),
                     s: Session = Depends(db.get_session)):
    """Scoped like the dashboard. It holds the plan, not subjects' values."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    m = matrix(s, protocol_id)
    generated = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    content = pdf.traceability(p.name, m["version"], "locked" if m["locked"] else "draft", generated, m["columns"], m["rows"])
    return _pdf(content, f"traceability_{protocol_id}_v{m['version']}")


@router.get("/api/subjects/{subject_ref}/pdf")
def casebook_pdf(subject_ref: int, cu: CurrentUser = Depends(require("listing.view")),
                 s: Session = Depends(db.get_session)):
    """Scoped like the listing. It holds values row by row, so it needs what the
    listing needs, not only report.pdf."""
    known = s.get(Subject, subject_ref)
    if known is None:
        raise HTTPException(404, "subject not found")
    p = scope.protocol_or_404(s, cu, known.protocol_id)
    subj = s.scalars(scope.visible_subjects(cu, p.id).where(Subject.id == subject_ref)).first()
    if subj is None:
        raise HTTPException(404, "subject not found")
    v, draft = _locked(s, p.id)
    units = {(form.visit, f.name): f.unit for form in draft.forms for f in form.fields}
    site = s.get(Organisation, subj.site_org_id)

    obs = list(s.scalars(scope.visible_observations(cu, p.id).where(Observation.subject_ref == subj.id)))
    ids = [o.id for o in obs]
    edits: dict[int, int] = {}
    for oid in s.scalars(select(ObservationHistory.observation_id).where(ObservationHistory.observation_id.in_(ids))):
        edits[oid] = edits.get(oid, 0) + 1
    live = list(s.scalars(select(Query).where(Query.subject_ref == subj.id, Query.status.in_(LIVE_QUERY))))
    by_obs: dict[int, int] = {}
    for q in live:
        if q.observation_id:
            by_obs[q.observation_id] = by_obs.get(q.observation_id, 0) + 1
    visit_of = {o.id: o.visit for o in obs}

    visits = []
    for visit in dict.fromkeys(form.visit for form in draft.forms):
        rows = sorted((o for o in obs if o.visit == visit), key=lambda o: (o.field_name, o.repeat_num))
        sg = valid_signoff(s, subj.id, visit)
        undone = s.scalars(select(Signoff).where(Signoff.subject_ref == subj.id, Signoff.visit == visit,
                                                 Signoff.invalidated_at.is_not(None))).all()
        visits.append({
            "visit": visit,
            "rows": [{"field": o.field_name, "repeat": o.repeat_num, "value": shown(o) if o.completion_status == "value" else o.completion_reason,
                      "unit": units.get((visit, o.field_name)), "status": o.status, "completion": o.completion_status.replace("_", " "),
                      "changes": edits.get(o.id, 0), "queries": by_obs.get(o.id, 0)} for o in rows],
            "open_queries": [q.text for q in live if (q.visit or visit_of.get(q.observation_id)) == visit],
            "signoff": {"who": sg.signed_by, "when": sg.signed_at.strftime("%Y-%m-%d %H:%M UTC"), "meaning": sg.meaning} if sg else None,
            "undone": [{"who": u.signed_by, "when": u.signed_at.strftime("%Y-%m-%d %H:%M UTC")} for u in undone],
        })
    s.add(UserAccessEvent(user_id=cu.user.id, action="export", by=cu.user.email, detail=f"casebook: {subj.code}"))
    s.commit()
    generated = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return _pdf(pdf.casebook(p.name, v.version, subj.code, site.code if site else "", generated, visits), f"casebook_{subj.code}")
