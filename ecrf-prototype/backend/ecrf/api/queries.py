"""Queries: the sponsor flags a value, the site answers or corrects it,
the sponsor closes it. While a query is open or answered the value is
'queried' and cannot be approved; closing returns it to 'entered'."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.api.data import EntryRequest, Reading, _locked_fields, record_change, shown, validate
from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import Observation, Organisation, Protocol, Query, Subject, utcnow

router = APIRouter(tags=["queries"])


class RaiseRequest(BaseModel):
    text: str


class AnswerRequest(BaseModel):
    text: str
    new_value: str | float | int | bool | None = None


def _visible_query(s: Session, cu: CurrentUser, query_id: int) -> tuple[Query, Observation]:
    q = s.get(Query, query_id)
    if q is None:
        raise HTTPException(404, "query not found")
    o = s.scalars(scope.visible_observations(cu, s.get(Observation, q.observation_id).protocol_id)
                  .where(Observation.id == q.observation_id)).first()
    if o is None:
        raise HTTPException(404, "query not found")
    return q, o


def _row(s: Session, q: Query, o: Observation) -> dict:
    p = s.get(Protocol, o.protocol_id)
    subj = s.get(Subject, o.subject_ref) if o.subject_ref else None
    site = s.get(Organisation, subj.site_org_id) if subj else None
    return {
        "id": q.id, "observation_id": o.id, "protocol_id": o.protocol_id,
        "protocol_name": p.name if p else None, "site": site.code if site else None,
        "subject": o.subject_id, "visit": o.visit, "field": o.field_name, "repeat": o.repeat_num,
        "value": shown(o), "observation_status": o.status,
        "status": q.status, "text": q.text, "raised_by": q.raised_by, "raised_at": q.raised_at.isoformat(),
        "answer_text": q.answer_text, "answered_by": q.answered_by,
        "answered_at": q.answered_at.isoformat() if q.answered_at else None,
        "closed_by": q.closed_by, "closed_at": q.closed_at.isoformat() if q.closed_at else None,
    }


@router.post("/api/data/{observation_id}/queries")
def raise_query(observation_id: int, body: RaiseRequest,
                cu: CurrentUser = Depends(require("query.raise")),
                s: Session = Depends(db.get_session)):
    o = s.get(Observation, observation_id)
    if o is None:
        raise HTTPException(404, "observation not found")
    scope.protocol_or_404(s, cu, o.protocol_id)
    if not body.text.strip():
        raise HTTPException(422, "say what the question is")
    live = s.scalars(select(Query).where(Query.observation_id == o.id, Query.status != "closed")).first()
    if live:
        raise HTTPException(409, f"query {live.id} is already {live.status} on this value")
    q = Query(observation_id=o.id, raised_by=cu.user.email, text=body.text.strip(), status="open")
    o.status = "queried"
    s.add(q)
    s.commit()
    return _row(s, q, o)


@router.post("/api/queries/{query_id}/answer")
def answer_query(query_id: int, body: AnswerRequest,
                 cu: CurrentUser = Depends(require("query.answer")),
                 s: Session = Depends(db.get_session)):
    """Own site only, which the scope lookup enforces as a 404. A corrected
    value goes through the same validation as data entry and the history
    row carries the query text as the reason."""
    q, o = _visible_query(s, cu, query_id)
    if q.status == "closed":
        raise HTTPException(409, "this query is closed")
    if body.new_value is not None and body.new_value != "":
        req = EntryRequest(protocol_id=o.protocol_id, subject_id=o.subject_id, visit=o.visit,
                           readings=[Reading(field_name=o.field_name, repeat_num=o.repeat_num,
                                             value=body.new_value)])
        _, _, _, fields = _locked_fields(s, cu, req)
        f = fields.get(o.field_name)
        if f is None:
            raise HTTPException(404, "field is no longer on the locked form")
        err = validate(f, body.new_value)
        if err:
            raise HTTPException(422, {"errors": {f"{o.field_name}#{o.repeat_num}": err}})
        num = float(body.new_value) if f.type in ("integer", "decimal") else None
        text = None if num is not None else str(body.new_value)
        record_change(s, o, num, text, cu.user.email, reason=f"query {q.id}: {q.text}")
    q.status, q.answer_text, q.answered_by, q.answered_at = "answered", body.text.strip(), cu.user.email, utcnow()
    s.commit()
    return _row(s, q, o)


@router.post("/api/queries/{query_id}/close")
def close_query(query_id: int, cu: CurrentUser = Depends(require("query.close")),
                s: Session = Depends(db.get_session)):
    q, o = _visible_query(s, cu, query_id)
    if q.status == "closed":
        return _row(s, q, o)
    q.status, q.closed_by, q.closed_at = "closed", cu.user.email, utcnow()
    # Back to 'entered': the value was questioned, so it is approved again
    # deliberately rather than inheriting an approval from before.
    if o.status == "queried":
        o.status, o.approved_by, o.approved_at = "entered", None, None
    s.commit()
    return _row(s, q, o)


@router.get("/api/queries")
def list_queries(status: str | None = None,
                 cu: CurrentUser = Depends(require("query.raise", "query.answer")),
                 s: Session = Depends(db.get_session)):
    """Scoped as everything else: sponsors see queries on their protocols,
    sites see queries on their own patients."""
    protocol_ids = [p.id for p in s.scalars(scope.visible_protocols(cu)).all()]
    out = []
    for pid in protocol_ids:
        obs = {o.id: o for o in s.scalars(scope.visible_observations(cu, pid)).all()}
        if not obs:
            continue
        q = select(Query).where(Query.observation_id.in_(list(obs)))
        if status:
            q = q.where(Query.status == status)
        for row in s.scalars(q.order_by(Query.raised_at.desc())).all():
            out.append(_row(s, row, obs[row.observation_id]))
    return out
