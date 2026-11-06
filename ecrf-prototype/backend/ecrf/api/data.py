"""Data entry by sites, and the sponsor's review of what was entered.

Validation runs here AND in the browser, on purpose. The browser check is
for immediate feedback; this one is the guarantee. Both read the same
locked field definition, so there is one source of truth.

Three rules live here:
  - a site enters data only for its own subjects, against a locked form
  - a value the sponsor has approved is frozen unless the sponsor reopens it
  - every change to a value writes a history row first
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf import derive
from ecrf.auth import scope
from ecrf.auth.permissions import DATA_READERS, CurrentUser, require
from ecrf.schema import DraftECRF, FieldDef
from ecrf.stats import seed as seed_mod
from ecrf.storage import db
from ecrf.storage.models import (
    Observation,
    ObservationHistory,
    Organisation,
    Query,
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


_TRUE = ("true", "yes", "1", "y")
_FALSE = ("false", "no", "0", "n")


def as_bool(value) -> bool | None:
    """Yes/no in any of the spellings the API accepts; None if it is neither."""
    if isinstance(value, bool):
        return value
    v = str(value).strip().lower()
    return True if v in _TRUE else False if v in _FALSE else None


def validate(field: FieldDef, value) -> str | None:
    """Return an error message, or None if valid. A blank is missing, and
    missing is an error only when the field is required; an explicit No,
    zero or empty choice is never confused with a blank."""
    if value is None or value == "":
        return "required" if field.required else None
    if field.type in ("integer", "decimal"):
        if isinstance(value, bool):
            return "must be a number"
        try:
            x = float(value)
        except (TypeError, ValueError):
            return "must be a number"
        if x != x or x in (float("inf"), float("-inf")):
            return "must be a number"
        if field.type == "integer" and x != int(x):
            return "must be a whole number"
        if field.min is not None and x < field.min:
            return f"below minimum {field.min}"
        if field.max is not None and x > field.max:
            return f"above maximum {field.max}"
    if field.type == "choice" and field.choices and str(value) not in field.choices:
        return f"must be one of: {', '.join(field.choices)}"
    if field.type == "boolean" and as_bool(value) is None:
        return "must be yes or no"
    if field.type == "date":
        try:
            d = date.fromisoformat(str(value))
        except ValueError:
            return "must be a date, YYYY-MM-DD"
        if not 1900 <= d.year <= date.today().year + 1:
            return "date is out of range"
    return None


def _raw(o: Observation):
    return o.value_num if o.value_num is not None else o.value_text


def _recompute(fields: dict[str, FieldDef], merged: dict[tuple[str, int], object],
               given: set[str], subj: Subject | None) -> list[Reading]:
    """Derived fields the submission did not itself state, worked out from
    the values now on file. Correcting a weight therefore moves the BMI."""
    inputs: dict[str, tuple[float, str | None]] = {}
    for (name, rep), value in merged.items():
        f = fields.get(name)
        if f is None or rep != 1 or f.type not in ("integer", "decimal") or value in (None, ""):
            continue
        key = derive.role_of(f, derive.INPUTS)
        if key and key not in inputs:
            try:
                inputs[key] = (float(value), f.unit)
            except (TypeError, ValueError):
                continue
    out = []
    computed = derive.compute(inputs, subj.birth_year if subj else None, subj.sex if subj else None, date.today().year)
    for d in computed:
        for f in fields.values():
            if f.name not in given and derive.role_of(f, derive.DERIVED) == d.key:
                value = round(d.value) if f.type == "integer" else d.value
                out.append(Reading(field_name=f.name, repeat_num=1, value=value))
    return out


def _prepare(s: Session, p, subj: Subject, visit: str, fields: dict[str, FieldDef], readings: list[Reading]):
    """What is on file for this visit, the derived values that follow from
    the submission, and every value as it would stand afterwards."""
    rows = {(o.field_name, o.repeat_num): o for o in s.scalars(select(Observation).where(
        Observation.protocol_id == p.id, Observation.subject_id == subj.code, Observation.visit == visit))}
    merged: dict[tuple[str, int], object] = {k: _raw(o) for k, o in rows.items()}
    merged.update({(r.field_name, r.repeat_num): r.value for r in readings})
    recomputed = _recompute(fields, merged, {r.field_name for r in readings}, subj)
    merged.update({(r.field_name, r.repeat_num): r.value for r in recomputed})
    return rows, recomputed, [Reading(field_name=k[0], repeat_num=k[1], value=v) for k, v in merged.items()]


def _check(fields: dict[str, FieldDef], readings: list[Reading], subj: Subject | None = None,
           standing: list[Reading] | None = None) -> dict:
    """`readings` are validated one by one; a derived value must then agree
    with the inputs in `standing`, the values as they would be after saving."""
    errors = {}
    for r in readings:
        f = fields.get(r.field_name)
        if not f:
            errors[f"{r.field_name}#{r.repeat_num}"] = "unknown field for this visit"
            continue
        err = validate(f, r.value)
        if err:
            errors[f"{r.field_name}#{r.repeat_num}"] = err
    if not errors:
        errors.update(derive.check(fields, standing if standing is not None else readings,
                                   subj.birth_year if subj else None,
                                   subj.sex if subj else None, date.today().year))
    return {"ok": not errors, "errors": errors}


def _split(field: FieldDef, value):
    """Numbers go in value_num, everything else in value_text. A yes/no is
    stored as the words Yes / No whatever spelling arrived, so the review
    table, the history and the statistics all read the same thing."""
    if value in (None, ""):
        return None, None
    if field.type in ("integer", "decimal"):
        return float(value), None
    if field.type == "boolean":
        return None, "Yes" if as_bool(value) else "No"
    return None, str(value)


def fmt_num(x: float) -> str:
    """138.0 is shown as 138; 25.5 stays 25.5."""
    return str(int(x)) if float(x).is_integer() else str(x)


def shown(o: Observation) -> str | None:
    """The value as text, for history rows and the review table."""
    if o.value_num is not None:
        return fmt_num(o.value_num)
    return o.value_text


def record_change(s: Session, o: Observation, num, text, by: str, reason: str | None) -> bool:
    """Write the history row, then change the value. Returns False when
    nothing changed, so an unchanged resubmission leaves no trace."""
    before = shown(o)
    after = fmt_num(num) if num is not None else text
    if before == after:
        return False
    s.add(ObservationHistory(observation_id=o.id, old_value=before, new_value=after,
                             changed_by=by, reason=reason))
    o.value_num, o.value_text = num, text
    o.updated_at = utcnow()
    return True


# ------------------------------------------------------------- site side

def save_readings(s: Session, cu: CurrentUser, p, v, subj: Subject, visit: str,
                  fields: dict[str, FieldDef], readings: list[Reading], reason: str | None = None) -> int:
    """The one path a value takes into the database, for data entry and for
    a correction through a query alike: same validation, same yes/no
    spelling, derived values recomputed, a history row for every change.

    An approved value is frozen. It reopens only when the sponsor raises a
    query on it, which sets 'queried'; an edit then takes it back to
    'submitted', so it has to be approved again. A value that was recomputed
    follows its inputs whatever its status, and needs approving again too."""
    rows, recomputed, standing = _prepare(s, p, subj, visit, fields, readings)
    check = _check(fields, [*readings, *recomputed], subj, standing)
    if not check["ok"]:
        raise HTTPException(422, {"errors": check["errors"]})

    blocked = [f"{r.field_name}#{r.repeat_num}" for r in readings
               if (o := rows.get((r.field_name, r.repeat_num))) is not None and o.status == "approved"]
    if blocked:
        raise HTTPException(409, {"approved": blocked,
                                  "message": "These values have been approved by the sponsor and can "
                                             "no longer be changed here. Ask the sponsor to raise a query."})

    auto = {r.field_name for r in recomputed}
    for r in [*readings, *recomputed]:
        f = fields[r.field_name]
        num, text = _split(f, r.value)
        o = rows.get((r.field_name, r.repeat_num))
        if o is None:
            s.add(Observation(protocol_id=p.id, subject_id=subj.code, subject_ref=subj.id,
                              ecrf_version_id=v.id, visit=visit, field_name=r.field_name,
                              repeat_num=r.repeat_num, value_num=num, value_text=text,
                              synthetic=True, status="submitted", entered_by=cu.user.email))
            continue
        why = "recalculated after a change to its inputs" if r.field_name in auto else reason
        changed = record_change(s, o, num, text, cu.user.email, why)
        if changed and o.approved_by:
            o.status, o.approved_by, o.approved_at = "submitted", None, None
    return len(readings)


# ------------------------------------------------------------- site side

@router.post("/validate")
def validate_only(body: EntryRequest, cu: CurrentUser = Depends(require("data.enter")),
                  s: Session = Depends(db.get_session)):
    p, _, subj, fields = _locked_fields(s, cu, body)
    _, recomputed, standing = _prepare(s, p, subj, body.visit, fields, body.readings)
    return _check(fields, [*body.readings, *recomputed], subj, standing)


@router.post("/enter")
def enter(body: EntryRequest, cu: CurrentUser = Depends(require("data.enter")),
          s: Session = Depends(db.get_session)):
    p, v, subj, fields = _locked_fields(s, cu, body)
    saved = save_readings(s, cu, p, v, subj, body.visit, fields, body.readings)
    s.commit()
    return {"saved": saved}


@router.post("/seed/{protocol_id}")
def seed(protocol_id: int, cu: CurrentUser = Depends(require("data.approve")),
         s: Session = Depends(db.get_session)):
    """Load synthetic observations for the dashboard demo, spread across
    the site organisations, all of them awaiting the sponsor's approval."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    v = db.locked_version(s, p.id)
    if v is None:
        raise HTTPException(409, "Lock the form before seeding; data only exists against a locked form")
    existing = s.scalars(select(Observation).where(Observation.protocol_id == protocol_id)).first()
    if existing:
        return {"seeded": 0, "already": True}
    sites = s.scalars(select(Organisation).where(Organisation.type == "site")
                      .order_by(Organisation.code)).all()[:2]
    if not sites:
        raise HTTPException(409, "No site organisations exist to own the synthetic subjects")
    n = seed_mod.seed(s, protocol_id, sites, v.id)
    s.commit()
    return {"seeded": n, "already": False}


@router.get("/{protocol_id}/subjects")
def subjects(protocol_id: int, cu: CurrentUser = Depends(require(*DATA_READERS)),
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
              status: str | None = None, cu: CurrentUser = Depends(require(*DATA_READERS)),
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
    live = set(s.scalars(select(Query.observation_id).where(
        Query.observation_id.in_(body.observation_ids), Query.status != "closed")))
    blocked = [o.id for o in rows if o.status == "queried" or (o.id in live and o.status != "approved")]
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
def history(protocol_id: int, observation_id: int, cu: CurrentUser = Depends(require(*DATA_READERS)),
            s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    o = s.scalars(scope.visible_observations(cu, protocol_id).where(Observation.id == observation_id)).first()
    if o is None:
        raise HTTPException(404, "observation not found")
    rows = s.scalars(select(ObservationHistory).where(ObservationHistory.observation_id == o.id)
                     .order_by(ObservationHistory.changed_at)).all()
    return [{"old_value": h.old_value, "new_value": h.new_value, "changed_by": h.changed_by,
             "changed_at": h.changed_at.isoformat(), "reason": h.reason} for h in rows]


