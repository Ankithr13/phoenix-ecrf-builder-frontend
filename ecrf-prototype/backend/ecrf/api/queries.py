"""Queries run both ways and at four levels.

A sponsor questions what a site entered; a site asks the sponsor about a
value, a visit, a patient or the study as a whole. The other side
answers (only a site may attach a corrected value, because data entry is
the site's job) and the sponsor closes it, whichever side raised it.

Every query belongs to one protocol and, so that a site only ever sees
its own traffic, to one site: the site that raised it, the site of the
patient it is about, or the site a sponsor chose to ask. When a query is
about one entered value that value cannot be approved while the query is
live; closing returns a queried value to 'submitted'. A site asking about a
value the sponsor already approved leaves the approval alone."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.api.data import EntryRequest, Reading, _locked_fields, save_readings, shown
from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import (
    Observation,
    Organisation,
    Protocol,
    ProtocolSite,
    Query,
    Subject,
    utcnow,
)

router = APIRouter(tags=["queries"])


class RaiseRequest(BaseModel):
    text: str


class NewQueryRequest(BaseModel):
    """What the query is about, from the widest to the narrowest. Only
    `protocol_id` and `text` are required; a sponsor asking without a
    patient must name the site."""
    protocol_id: int
    text: str
    site_org_id: int | None = None
    subject_code: str | None = None
    visit: str | None = None
    observation_id: int | None = None


class AnswerRequest(BaseModel):
    text: str
    new_value: str | float | int | bool | None = None


# ------------------------------------------------------------- helpers

def _about(q: Query) -> str:
    if q.observation_id:
        return "value"
    if q.visit and q.subject_ref:
        return "visit"
    if q.subject_ref:
        return "patient"
    return "study"


def _row(s: Session, q: Query, cu: CurrentUser | None = None) -> dict:
    p = s.get(Protocol, q.protocol_id)
    o = s.get(Observation, q.observation_id) if q.observation_id else None
    subj = s.get(Subject, q.subject_ref) if q.subject_ref else None
    site = s.get(Organisation, q.site_org_id) if q.site_org_id else None
    mine = cu is not None and cu.org.type == q.raised_by_org
    can_answer = cu is not None and q.status != "closed" and not mine
    can_close = cu is not None and q.status != "closed" and cu.can("query.close")
    return {
        "id": q.id, "protocol_id": q.protocol_id, "protocol_name": p.name if p else None,
        "about": _about(q),
        "site": site.code if site else None, "site_name": site.name if site else None,
        "subject": subj.code if subj else (o.subject_id if o else None),
        "visit": q.visit or (o.visit if o else None),
        "observation_id": o.id if o else None,
        "field": o.field_name if o else None, "repeat": o.repeat_num if o else None,
        "value": shown(o) if o else None, "observation_status": o.status if o else None,
        "status": q.status, "text": q.text,
        "raised_by": q.raised_by, "raised_by_org": q.raised_by_org, "raised_at": q.raised_at.isoformat(),
        "answer_text": q.answer_text, "answered_by": q.answered_by,
        "answered_at": q.answered_at.isoformat() if q.answered_at else None,
        "closed_by": q.closed_by, "closed_at": q.closed_at.isoformat() if q.closed_at else None,
        # For the caller: whether it is their turn to answer, or theirs to close.
        "can_answer": can_answer, "can_close": can_close,
        "for_me": (can_answer and q.status == "open") or (can_close and q.status == "answered"),
    }


def _visible_queries(s: Session, cu: CurrentUser, protocol_id: int):
    q = select(Query).where(Query.protocol_id == protocol_id)
    if cu.org.type == "site":
        q = q.where(Query.site_org_id == cu.org.id)
    return q


def _visible_query(s: Session, cu: CurrentUser, query_id: int) -> Query:
    q = s.get(Query, query_id)
    if q is None:
        raise HTTPException(404, "query not found")
    if s.scalars(scope.visible_protocols(cu).where(Protocol.id == q.protocol_id)).first() is None:
        raise HTTPException(404, "query not found")
    if cu.org.type == "site" and q.site_org_id != cu.org.id:
        raise HTTPException(404, "query not found")
    return q


def _create(s: Session, cu: CurrentUser, body: NewQueryRequest) -> Query:
    p = scope.protocol_or_404(s, cu, body.protocol_id)
    if not body.text.strip():
        raise HTTPException(422, "say what the question is")

    o = subj = None
    if body.observation_id is not None:
        o = s.scalars(scope.visible_observations(cu, p.id).where(Observation.id == body.observation_id)).first()
        if o is None:
            raise HTTPException(404, "observation not found")
        subj = s.get(Subject, o.subject_ref) if o.subject_ref else None
        live = s.scalars(select(Query).where(Query.observation_id == o.id, Query.status != "closed")).first()
        if live:
            raise HTTPException(409, f"query {live.id} is already {live.status} on this value")
    elif body.subject_code:
        subj = s.scalars(scope.visible_subjects(cu, p.id).where(Subject.code == body.subject_code.strip().upper())).first()
        if subj is None:
            raise HTTPException(404, "patient not found")

    visit = (body.visit or "").strip() or (o.visit if o else None)
    if visit and not o:
        visits = {f["visit"] for v in [db.locked_version(s, p.id)] if v for f in v.content.get("forms", [])}
        if visits and visit not in visits:
            raise HTTPException(422, f"{visit} is not a visit on this form")

    # Which site this query belongs to.
    if cu.org.type == "site":
        site_id = cu.org.id
    elif subj is not None:
        site_id = subj.site_org_id
    elif body.site_org_id is not None:
        assigned = s.scalars(select(ProtocolSite).where(ProtocolSite.protocol_id == p.id,
                                                        ProtocolSite.site_org_id == body.site_org_id)).first()
        if assigned is None:
            raise HTTPException(422, "that site is not assigned to this study")
        site_id = body.site_org_id
    else:
        raise HTTPException(422, "say which site the question is for, or pick a patient")

    q = Query(protocol_id=p.id, site_org_id=site_id, subject_ref=subj.id if subj else None,
              visit=visit if (visit and not o) else None, observation_id=o.id if o else None,
              raised_by=cu.user.email, raised_by_org=cu.org.type, text=body.text.strip(), status="open")
    # A site's question must not undo the sponsor's approval; only a question
    # from the sponsor reopens an approved value.
    if o is not None and (cu.org.type == "sponsor" or o.status != "approved"):
        o.status = "queried"
    s.add(q)
    s.commit()
    return q


# -------------------------------------------------------------- routes

@router.post("/api/queries")
def new_query(body: NewQueryRequest, cu: CurrentUser = Depends(require("query.raise")),
              s: Session = Depends(db.get_session)):
    """Either side, at any level: study, patient, visit, or one value."""
    q = _create(s, cu, body)
    return _row(s, q, cu)


@router.post("/api/data/{observation_id}/queries")
def raise_query(observation_id: int, body: RaiseRequest,
                cu: CurrentUser = Depends(require("query.raise")),
                s: Session = Depends(db.get_session)):
    """Shortcut from a value on screen."""
    o = s.get(Observation, observation_id)
    if o is None:
        raise HTTPException(404, "observation not found")
    q = _create(s, cu, NewQueryRequest(protocol_id=o.protocol_id, observation_id=o.id, text=body.text))
    return _row(s, q, cu)


@router.post("/api/queries/{query_id}/answer")
def answer_query(query_id: int, body: AnswerRequest,
                 cu: CurrentUser = Depends(require("query.answer")),
                 s: Session = Depends(db.get_session)):
    """The side that did not raise it answers. Out of scope is a 404. A
    corrected value may only come from a site, only when the query is
    about one value, and goes through the same validation as data entry;
    the history row carries the query text as the reason."""
    q = _visible_query(s, cu, query_id)
    if q.status == "closed":
        raise HTTPException(409, "this query is closed")
    if cu.org.type == q.raised_by_org:
        raise HTTPException(403, "your side raised this query; the other side answers it")
    has_value = body.new_value is not None and body.new_value != ""
    if has_value and cu.org.type != "site":
        raise HTTPException(403, "only the site may change an entered value; answer in words")
    if has_value and not q.observation_id:
        raise HTTPException(422, "this query is not about one value, so there is nothing to correct")
    if has_value:
        o = s.get(Observation, q.observation_id)
        req = EntryRequest(protocol_id=o.protocol_id, subject_id=o.subject_id, visit=o.visit, readings=[])
        p, v, subj, fields = _locked_fields(s, cu, req)
        if fields.get(o.field_name) is None:
            raise HTTPException(404, "field is no longer on the locked form")
        save_readings(s, cu, p, v, subj, o.visit, fields,
                      [Reading(field_name=o.field_name, repeat_num=o.repeat_num, value=body.new_value)],
                      reason=f"query {q.id}: {q.text}")
    q.status, q.answer_text, q.answered_by, q.answered_at = "answered", body.text.strip(), cu.user.email, utcnow()
    s.commit()
    return _row(s, q, cu)


@router.post("/api/queries/{query_id}/close")
def close_query(query_id: int, cu: CurrentUser = Depends(require("query.close")),
                s: Session = Depends(db.get_session)):
    """Only the sponsor closes, whichever side raised it. The permission is
    the rule: a site has no route to end a question about its own data."""
    q = _visible_query(s, cu, query_id)
    if q.status == "closed":
        return _row(s, q, cu)
    q.status, q.closed_by, q.closed_at = "closed", cu.user.email, utcnow()
    # Back to 'submitted': the value was questioned, so it is approved again
    # deliberately rather than inheriting an approval from before.
    if q.observation_id:
        o = s.get(Observation, q.observation_id)
        if o is not None and o.status == "queried":
            o.status, o.approved_by, o.approved_at = "submitted", None, None
    s.commit()
    return _row(s, q, cu)


@router.get("/api/queries")
def list_queries(status: str | None = None,
                 cu: CurrentUser = Depends(require("query.raise", "query.answer")),
                 s: Session = Depends(db.get_session)):
    """Scoped as everything else: sponsors see queries on their protocols,
    sites see queries that belong to their site."""
    out = []
    for p in s.scalars(scope.visible_protocols(cu)).all():
        q = _visible_queries(s, cu, p.id)
        if status:
            q = q.where(Query.status == status)
        for row in s.scalars(q.order_by(Query.raised_at.desc())).all():
            out.append(_row(s, row, cu))
    return out
