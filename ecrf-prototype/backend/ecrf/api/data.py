"""Data entry by sites, and the sponsor's review of what was entered.

Validation runs here AND in the browser, on purpose. The browser check is
for immediate feedback; this one is the guarantee. Both read the same
locked field definition, so there is one source of truth.

Three rules live here:
  - a site enters data only for its own subjects, against a locked form
  - a value the sponsor has approved cannot be changed by the site
  - every change to a value writes a history row first
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.schema import DraftECRF, FieldDef
from ecrf.stats import seed as seed_mod
from ecrf.storage import db
from ecrf.storage.models import (
    Observation,
    ObservationHistory,
    Organisation,
    Subject,
    utcnow,
)

router = APIRouter(prefix="/api/data", tags=["data"])
review_router = APIRouter(prefix="/api/protocols", tags=["data review"])


class Reading(BaseModel):
    field_name: str
    repeat_num: int = 1
    value: str | float | int | bool | None


class EntryRequest(BaseModel):
    protocol_id: int
    subject_id: str          # the subject code, e.g. BGH-001
    visit: str
    readings: list[Reading]


# ---------------------------------------------------------------- helpers

def _locked_fields(s: Session, cu: CurrentUser, body: EntryRequest):
    """The protocol, its locked version, the subject, and the approved field
    definitions for the visit. Any of them missing is the caller's 404/409."""
    p = scope.protocol_or_404(s, cu, body.protocol_id)
    v = db.locked_version(s, p.id)
    if v is None:
        raise HTTPException(409, "The form is not locked yet, so no data can be entered against it")
    subj = scope.subject_or_404(s, cu, p.id, body.subject_id)
    draft = DraftECRF.model_validate(v.content)
    for form in draft.forms:
        if form.visit == body.visit:
            return p, v, subj, {f.name: f for f in form.fields if f.status == "approved"}
    raise HTTPException(404, f"visit '{body.visit}' not in eCRF")


def validate(field: FieldDef, value) -> str | None:
    """Return an error message, or None if valid."""
    if value is None or value == "":
        return "required" if field.required else None
    if field.type in ("integer", "decimal"):
        try:
            x = float(value)
        except (TypeError, ValueError):
            return "must be a number"
        if field.type == "integer" and x != int(x):
            return "must be a whole number"
        if field.min is not None and x < field.min:
            return f"below minimum {field.min}"
        if field.max is not None and x > field.max:
            return f"above maximum {field.max}"
    if field.type == "choice" and field.choices and str(value) not in field.choices:
        return f"must be one of: {', '.join(field.choices)}"
    if field.type == "boolean" and str(value).lower() not in ("true", "false", "yes", "no", "1", "0"):
        return "must be yes or no"
    return None


def _check(fields: dict[str, FieldDef], readings: list[Reading]) -> dict:
    errors = {}
    for r in readings:
        f = fields.get(r.field_name)
        if not f:
            errors[f"{r.field_name}#{r.repeat_num}"] = "unknown field for this visit"
            continue
        err = validate(f, r.value)
        if err:
            errors[f"{r.field_name}#{r.repeat_num}"] = err
    return {"ok": not errors, "errors": errors}


def _split(field: FieldDef, value):
    num = float(value) if field.type in ("integer", "decimal") and value not in (None, "") else None
    text = None if num is not None else (str(value) if value not in (None, "") else None)
    return num, text


def shown(o: Observation) -> str | None:
    """The value as text, for history rows and the review table."""
    if o.value_num is not None:
        return str(o.value_num)
    return o.value_text


def record_change(s: Session, o: Observation, num, text, by: str, reason: str | None) -> bool:
    """Write the history row, then change the value. Returns False when
    nothing changed, so an unchanged resubmission leaves no trace."""
    before = shown(o)
    after = str(num) if num is not None else text
    if before == after:
        return False
    s.add(ObservationHistory(observation_id=o.id, old_value=before, new_value=after,
                             changed_by=by, reason=reason))
    o.value_num, o.value_text = num, text
    o.updated_at = utcnow()
    return True


# ------------------------------------------------------------- site side

@router.post("/validate")
def validate_only(body: EntryRequest, cu: CurrentUser = Depends(require("data.enter")),
                  s: Session = Depends(db.get_session)):
    _, _, _, fields = _locked_fields(s, cu, body)
    return _check(fields, body.readings)


@router.post("/enter")
def enter(body: EntryRequest, cu: CurrentUser = Depends(require("data.enter")),
          s: Session = Depends(db.get_session)):
    p, v, subj, fields = _locked_fields(s, cu, body)
    check = _check(fields, body.readings)
    if not check["ok"]:
        raise HTTPException(422, {"errors": check["errors"]})
    saved, blocked = 0, []
    for r in body.readings:
        f = fields[r.field_name]
        num, text = _split(f, r.value)
        existing = s.scalars(select(Observation).where(
            Observation.protocol_id == p.id, Observation.subject_id == subj.code,
            Observation.visit == body.visit, Observation.field_name == r.field_name,
            Observation.repeat_num == r.repeat_num)).first()
        if existing:
            # Approved data belongs to the sponsor now. The site can change
            # it again only through a query (stage 5), which sets 'queried'.
            if existing.status == "approved":
                blocked.append(f"{r.field_name}#{r.repeat_num}")
                continue
            record_change(s, existing, num, text, cu.user.email, None)
        else:
            s.add(Observation(protocol_id=p.id, subject_id=subj.code, subject_ref=subj.id,
                              ecrf_version_id=v.id, visit=body.visit, field_name=r.field_name,
                              repeat_num=r.repeat_num, value_num=num, value_text=text,
                              synthetic=True, status="entered", entered_by=cu.user.email))
        saved += 1
    if blocked:
        s.rollback()
        raise HTTPException(409, {"approved": blocked,
                                  "message": "These values have been approved by the sponsor and can "
                                             "no longer be changed here. Ask the sponsor to raise a query."})
    s.commit()
    return {"saved": saved}


@router.post("/seed/{protocol_id}")
def seed(protocol_id: int, cu: CurrentUser = Depends(require("data.seed")),
         s: Session = Depends(db.get_session)):
    """Load synthetic observations for the dashboard demo, spread across
    the site organisations, about 70% of them already approved."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    existing = s.scalars(select(Observation).where(Observation.protocol_id == protocol_id)).first()
    if existing:
        return {"seeded": 0, "already": True}
    sites = s.scalars(select(Organisation).where(Organisation.type == "site")
                      .order_by(Organisation.code)).all()[:2]
    if not sites:
        raise HTTPException(409, "No site organisations exist to own the synthetic subjects")
    v = db.latest_version(s, p.id)
    n = seed_mod.seed(s, protocol_id, sites, v.id if v else None)
    s.commit()
    return {"seeded": n, "already": False}


@router.get("/{protocol_id}/subjects")
def subjects(protocol_id: int, cu: CurrentUser = Depends(require("data.view")),
             s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    rows = s.execute(
        scope.visible_observations(cu, protocol_id)
        .with_only_columns(Observation.subject_id, Observation.visit).distinct()
    ).all()
    out: dict[str, list[str]] = {}
    for subj, visit in rows:
        out.setdefault(subj, []).append(visit)
    return [{"subject_id": k, "visits": v} for k, v in sorted(out.items())]


# ---------------------------------------------------------- sponsor side

class ApproveRequest(BaseModel):
    observation_ids: list[int]


def _row(s: Session, o: Observation, sites: dict[int, Organisation]) -> dict:
    subj = s.get(Subject, o.subject_ref) if o.subject_ref else None
    site = sites.get(subj.site_org_id) if subj else None
    return {
        "id": o.id, "site": site.code if site else None, "subject": o.subject_id,
        "visit": o.visit, "field": o.field_name, "repeat": o.repeat_num, "value": shown(o),
        "status": o.status, "entered_by": o.entered_by, "entered_at": o.entered_at.isoformat(),
        "updated_at": o.updated_at.isoformat() if o.updated_at else None,
        "approved_by": o.approved_by,
    }


@review_router.get("/{protocol_id}/data")
def list_data(protocol_id: int, site: str | None = None, visit: str | None = None,
              status: str | None = None, cu: CurrentUser = Depends(require("data.view")),
              s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    q = scope.visible_observations(cu, protocol_id)
    if visit:
        q = q.where(Observation.visit == visit)
    if status:
        q = q.where(Observation.status == status)
    sites = {o.id: o for o in s.scalars(select(Organisation).where(Organisation.type == "site"))}
    rows = [_row(s, o, sites) for o in s.scalars(q.order_by(Observation.subject_id, Observation.visit,
                                                              Observation.field_name, Observation.repeat_num))]
    if site:
        rows = [r for r in rows if r["site"] == site]
    return rows


@review_router.post("/{protocol_id}/data/approve")
def approve_data(protocol_id: int, body: ApproveRequest,
                 cu: CurrentUser = Depends(require("data.approve")),
                 s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    rows = s.scalars(select(Observation).where(Observation.protocol_id == protocol_id,
                                                Observation.id.in_(body.observation_ids))).all()
    blocked = [o.id for o in rows if o.status == "queried"]
    if blocked:
        raise HTTPException(409, {"queried": blocked,
                                  "message": "Close the open queries on these values before approving them"})
    now = utcnow()
    for o in rows:
        if o.status != "approved":
            o.status, o.approved_by, o.approved_at = "approved", cu.user.email, now
    s.commit()
    return {"approved": len(rows)}


@review_router.get("/{protocol_id}/data/{observation_id}/history")
def history(protocol_id: int, observation_id: int, cu: CurrentUser = Depends(require("data.view")),
            s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    o = s.scalars(scope.visible_observations(cu, protocol_id).where(Observation.id == observation_id)).first()
    if o is None:
        raise HTTPException(404, "observation not found")
    rows = s.scalars(select(ObservationHistory).where(ObservationHistory.observation_id == o.id)
                     .order_by(ObservationHistory.changed_at)).all()
    return [{"old_value": h.old_value, "new_value": h.new_value, "changed_by": h.changed_by,
             "changed_at": h.changed_at.isoformat(), "reason": h.reason} for h in rows]


