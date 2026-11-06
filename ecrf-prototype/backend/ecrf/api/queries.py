"""Queries run both ways and at four levels.

A sponsor questions what a site entered; a site asks the sponsor about a
value, a visit, a patient or the study as a whole. The other side
answers (only a site may attach a corrected value, because data entry is
the site's job) and the sponsor closes it, whichever side raised it. A status
is open, answered, closed or cancelled.

Every query belongs to one protocol and, so that a site only ever sees
its own traffic, to one site: the site that raised it, the site of the
patient it is about, or the site a sponsor chose to ask. A value keeps its
status while a query is on it; it cannot be approved until the query is
closed. An approved value can change only while the sponsor has one open, so
a site asking about it leaves the approval alone. Edit checks raise queries
here too, with raised_by "system"."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf import notify
from ecrf.api.data import (
    EntryRequest,
    Reading,
    _locked_fields,
    open_query_counts,
    save_readings,
    shown,
)
from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import (
    LIVE_QUERY,
    Observation,
    ObservationHistory,
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


def _may_answer(cu: CurrentUser, q: Query) -> bool:
    """The side that did not raise it. On the site side that is query.answer.
    The matrix gives the sponsor side no query.answer, but a site's question
    still needs a reply, so whoever may close one may reply to it in words."""
    if cu.org.type == q.raised_by_org:
        return False
    return cu.can("query.answer") if cu.org.type == "site" else cu.can("query.close")


def _value_unchanged(s: Session, q: Query) -> bool:
    """True for a query about one value when that value has not changed since."""
    if not q.observation_id:
        return False
    return s.scalars(select(ObservationHistory.id).where(
        ObservationHistory.observation_id == q.observation_id,
        ObservationHistory.changed_at >= q.raised_at)).first() is None


def _row(s: Session, q: Query, cu: CurrentUser | None = None) -> dict:
    p = s.get(Protocol, q.protocol_id)
    o = s.get(Observation, q.observation_id) if q.observation_id else None
    subj = s.get(Subject, q.subject_ref) if q.subject_ref else None
    site = s.get(Organisation, q.site_org_id) if q.site_org_id else None
    live = q.status in LIVE_QUERY
    can_answer = cu is not None and live and _may_answer(cu, q)
    can_close = cu is not None and live and cu.can("query.close")
    return {
        "id": q.id, "protocol_id": q.protocol_id, "protocol_name": p.name if p else None,
        "about": _about(q),
        "site": site.code if site else None, "site_name": site.name if site else None,
        "subject": subj.code if subj else (o.subject_id if o else None),
        "visit": q.visit or (o.visit if o else None),
        "observation_id": o.id if o else None,
        "field": o.field_name if o else None, "repeat": o.repeat_num if o else None,
        "value": shown(o) if o else None, "observation_status": o.status if o else None,
        "open_query_count": open_query_counts(s, [o.id]).get(o.id, 0) if o else 0,
        "check_code": q.check_code,
        "status": q.status, "text": q.text,
        "raised_by": q.raised_by, "raised_by_org": q.raised_by_org, "raised_at": q.raised_at.isoformat(),
        "answer_text": q.answer_text, "answered_by": q.answered_by,
        "answered_at": q.answered_at.isoformat() if q.answered_at else None,
        "closed_by": q.closed_by, "closed_at": q.closed_at.isoformat() if q.closed_at else None,
        "close_reason": q.close_reason, "raised_by_role": q.raised_by_role,
        "cancelled_at": q.cancelled_at.isoformat() if q.cancelled_at else None, "cancel_reason": q.cancel_reason,
        "can_cancel": cu is not None and live and cu.org.type == "sponsor" and q.raised_by == cu.user.email,
        "needs_close_reason": live and _value_unchanged(s, q),
        # For the caller: whether it is their turn to answer, or theirs to close.
        "can_answer": can_answer, "can_close": can_close,
        "for_me": (can_answer and q.status == "open") or (can_close and q.status == "answered"),
    }


def _visible_queries(s: Session, cu: CurrentUser, protocol_id: int):
    q = select(Query).where(Query.protocol_id == protocol_id)
    if cu.site_ids is not None:
        q = q.where(Query.site_org_id.in_(cu.site_ids))
    return q


def _visible_query(s: Session, cu: CurrentUser, query_id: int) -> Query:
    q = s.get(Query, query_id)
    if q is None:
        raise HTTPException(404, "query not found")
    if s.scalars(scope.visible_protocols(cu).where(Protocol.id == q.protocol_id)).first() is None:
        raise HTTPException(404, "query not found")
    if cu.site_ids is not None and q.site_org_id not in cu.site_ids:
        raise HTTPException(404, "query not found")
    return q


def _create(s: Session, cu: CurrentUser, body: NewQueryRequest) -> Query:
    p = scope.protocol_or_404(s, cu, body.protocol_id)
    scope.check_study_open(p)
    if not body.text.strip():
        raise HTTPException(422, "say what the question is")

    o = subj = None
    if body.observation_id is not None:
        o = s.scalars(scope.visible_observations(cu, p.id).where(Observation.id == body.observation_id)).first()
        if o is None:
            raise HTTPException(404, "observation not found")
        subj = s.get(Subject, o.subject_ref) if o.subject_ref else None
        live = s.scalars(select(Query).where(Query.observation_id == o.id, Query.status.in_(LIVE_QUERY))).first()
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
        if cu.site_ids is not None and body.site_org_id not in cu.site_ids:
            raise HTTPException(404, "site not found")
        assigned = s.scalars(select(ProtocolSite).where(ProtocolSite.protocol_id == p.id,
                                                        ProtocolSite.site_org_id == body.site_org_id)).first()
        if assigned is None:
            raise HTTPException(422, "that site is not assigned to this study")
        site_id = body.site_org_id
    else:
        raise HTTPException(422, "say which site the question is for, or pick a patient")

    q = Query(protocol_id=p.id, site_org_id=site_id, subject_ref=subj.id if subj else None,
              visit=visit if (visit and not o) else None, observation_id=o.id if o else None,
              raised_by=cu.user.email, raised_by_org=cu.org.type, raised_by_role=cu.role,
              text=body.text.strip(), status="open")
    s.add(q)
    s.flush()
    notify.query_raised(s, p, q, subj.code if subj else None)
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
                 cu: CurrentUser = Depends(require("query.answer", "query.close")),
                 s: Session = Depends(db.get_session)):
    """The side that did not raise it answers. Out of scope is a 404. A
    corrected value may only come from a site, only when the query is
    about one value, and goes through the same validation as data entry;
    the history row carries the query text as the reason."""
    q = _visible_query(s, cu, query_id)
    scope.check_study_open(s.get(Protocol, q.protocol_id))
    if q.status not in LIVE_QUERY:
        raise HTTPException(409, f"this query is {q.status}")
    if not _may_answer(cu, q):
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
    subj = s.get(Subject, q.subject_ref) if q.subject_ref else None
    notify.query_answered(s, s.get(Protocol, q.protocol_id), q, subj.code if subj else None)
    s.commit()
    return _row(s, q, cu)


class CloseRequest(BaseModel):
    reason: str | None = None


@router.post("/api/queries/{query_id}/close")
def close_query(query_id: int, body: CloseRequest | None = None,
                cu: CurrentUser = Depends(require("query.close")),
                s: Session = Depends(db.get_session)):
    """Only the sponsor closes, whichever side raised it. The permission is
    the rule: a site has no route to end a question about its own data. Closing
    a query about a value that did not change says why."""
    q = _visible_query(s, cu, query_id)
    scope.check_study_open(s.get(Protocol, q.protocol_id))
    if q.status == "closed":
        return _row(s, q, cu)
    if q.status not in LIVE_QUERY:
        raise HTTPException(409, f"this query is {q.status}")
    reason = ((body.reason if body else None) or "").strip()
    if _value_unchanged(s, q) and not reason:
        raise HTTPException(422, "The value has not changed, so closing this query needs a reason")
    q.status, q.closed_by, q.closed_at, q.close_reason = "closed", cu.user.email, utcnow(), reason or None
    s.commit()
    return _row(s, q, cu)


class CancelRequest(BaseModel):
    reason: str


@router.post("/api/queries/{query_id}/cancel")
def cancel_query(query_id: int, body: CancelRequest, cu: CurrentUser = Depends(require("query.raise")),
                 s: Session = Depends(db.get_session)):
    """A sponsor role can withdraw a query they raised themselves, with a reason."""
    q = _visible_query(s, cu, query_id)
    scope.check_study_open(s.get(Protocol, q.protocol_id))
    if cu.org.type != "sponsor" or q.raised_by != cu.user.email:
        raise HTTPException(403, "Only the person on the sponsor side who raised a query can cancel it")
    if q.status not in LIVE_QUERY:
        raise HTTPException(409, f"this query is {q.status}")
    if not body.reason.strip():
        raise HTTPException(422, "Cancelling a query needs a reason")
    q.status, q.cancelled_at, q.cancel_reason = "cancelled", utcnow(), body.reason.strip()
    s.commit()
    return _row(s, q, cu)


@router.get("/api/queries")
def list_queries(status: str | None = None,
                 cu: CurrentUser = Depends(require("query.raise", "query.answer", "query.close")),
                 s: Session = Depends(db.get_session)):
    """Scoped as everything else: sponsors see queries on their protocols,
    sites and monitors see queries that belong to their sites."""
    out = []
    for p in s.scalars(scope.visible_protocols(cu)).all():
        q = _visible_queries(s, cu, p.id)
        if status:
            q = q.where(Query.status == status)
        for row in s.scalars(q.order_by(Query.raised_at.desc())).all():
            out.append(_row(s, row, cu))
    return out
