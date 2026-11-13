"""Data entry by sites, and the sponsor's review of what was entered.

Validation runs here AND in the browser, on purpose. The browser check is
for immediate feedback; this one is the guarantee. Both read the same
locked field definition, so there is one source of truth.

Rules that live here:
  - a site enters data only for its own subjects, against a locked form
  - entered values are drafts until the site submits the visit
  - editing a submitted or approved value needs a reason
  - a value the sponsor has approved is frozen unless the sponsor reopens it
  - every change to a value writes a history row first

Only what a value physically cannot be stops a save: a word in a number field.
A value out of range or a blank required field is a soft check, which raises a
query at submit and never overwrites what was entered.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf import clock, derive, notify
from ecrf.auth import scope
from ecrf.auth.permissions import DATA_READERS, CurrentUser, require
from ecrf.checks import run as checks
from ecrf.schema import DraftECRF, FieldDef
from ecrf.stats import seed as seed_mod
from ecrf.storage import db
from ecrf.storage.models import (
    LIVE_QUERY,
    Observation,
    ObservationHistory,
    Organisation,
    Query,
    Signoff,
    Subject,
    utcnow,
)

router = APIRouter(prefix="/api/data", tags=["data"])
review_router = APIRouter(prefix="/api/protocols", tags=["data review"])


class Reading(BaseModel):
    field_name: str
    repeat_num: int = 1
    value: str | float | int | bool | None = None
    completion_status: str = "value"
    completion_reason: str | None = None


class EntryRequest(BaseModel):
    protocol_id: int
    subject_id: str          # the subject code, e.g. BGH-001
    visit: str
    readings: list[Reading]
    # Why, when this changes a value that has already been submitted.
    reason: str | None = None


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
            return p, v, subj, {f.name: f for f in form.fields if f.status == "approved" and f.collected}
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
    """What this value cannot be, whatever the protocol says. A blank passes
    here: a missing required value is a soft check at submit. So does a number
    out of range. An explicit No or zero is never confused with a blank."""
    if value is None or value == "":
        return None
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
    if field.type == "choice" and field.choices and str(value) not in field.choices:
        return f"must be one of: {', '.join(field.choices)}"
    if field.type == "boolean" and as_bool(value) is None:
        return "must be yes or no"
    if field.type == "date":
        try:
            d = date.fromisoformat(str(value))
        except ValueError:
            return "must be a date, YYYY-MM-DD"
        if not 1900 <= d.year <= clock.today().year + 1:
            return "date is out of range"
    return None


_COMPLETIONS = {"not_done": ("allow_not_done", "Not done"), "not_applicable": ("allow_not_applicable", "Not applicable"),
                "unknown": ("allow_unknown", "Unknown")}


def _completion_error(field: FieldDef, r: Reading) -> str | None:
    """Not done, Not applicable and Unknown only where the form allows them,
    each with a reason, and never alongside a value."""
    if r.completion_status == "value":
        return None
    if r.completion_status not in _COMPLETIONS:
        return "unknown completion status"
    allowed, label = _COMPLETIONS[r.completion_status]
    if not getattr(field, allowed):
        return f"{label} is not allowed on this field"
    if not (r.completion_reason or "").strip():
        return f"{label} needs a reason"
    if r.value not in (None, ""):
        return f"{label} cannot have a value as well"
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
        if f is None or rep != 1:
            continue
        key = derive.role_of(f, derive.INPUTS)
        number = derive.input_value(f, value) if key else None
        if number is not None and key not in inputs:
            inputs[key] = (number, f.unit)
    out = []
    computed = derive.compute(inputs, subj.birth_year if subj else None, subj.sex if subj else None, clock.today().year)
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
    # How each value was completed travels with it: a field marked Not done is
    # answered, even though it has no value.
    completion = {k: (o.completion_status, o.completion_reason) for k, o in rows.items()}
    completion.update({(r.field_name, r.repeat_num): (r.completion_status, r.completion_reason) for r in readings})
    standing = [Reading(field_name=k[0], repeat_num=k[1], value=v,
                        completion_status=completion.get(k, ("value", None))[0],
                        completion_reason=completion.get(k, ("value", None))[1]) for k, v in merged.items()]
    return rows, recomputed, standing


VISIT_DATE_CODE = "SVSTDTC"
VISIT_NOT_PERFORMED = "Visit not performed"


def _visit_not_performed(s: Session, p, subj: Subject, visit: str, fields: dict[str, FieldDef],
                         readings: list[Reading]) -> list[Reading]:
    """A visit date marked Not done means the visit did not happen, so every
    other field at the visit becomes Not applicable. Correcting the date back to
    a real one lifts that again, and only from the fields this put there."""
    visit_date = next((f for f in fields.values() if f.cdash == VISIT_DATE_CODE), None)
    given = next((r for r in readings if visit_date and r.field_name == visit_date.name), None)
    if given is None:
        return []
    taken = {(r.field_name, r.repeat_num) for r in readings}
    if given.completion_status == "not_done":
        return [Reading(field_name=f.name, repeat_num=n, completion_status="not_applicable",
                        completion_reason=VISIT_NOT_PERFORMED)
                for f in fields.values() if f is not visit_date
                for n in range(1, max(1, f.repeats) + 1) if (f.name, n) not in taken]
    if given.completion_status != "value":
        return []
    rows = s.scalars(select(Observation).where(Observation.protocol_id == p.id, Observation.subject_ref == subj.id,
                                               Observation.visit == visit,
                                               Observation.completion_status == "not_applicable",
                                               Observation.completion_reason == VISIT_NOT_PERFORMED)).all()
    return [Reading(field_name=o.field_name, repeat_num=o.repeat_num) for o in rows
            if (o.field_name, o.repeat_num) not in taken]


def _check(fields: dict[str, FieldDef], readings: list[Reading], subj: Subject | None = None,
           standing: list[Reading] | None = None, cascaded: list[Reading] | None = None) -> dict:
    """`readings` are validated one by one; a derived value must then agree
    with the inputs in `standing`, the values as they would be after saving.
    `cascaded` came from the visit date, not from a person, so a field need not
    offer Not applicable to receive it."""
    errors = {}
    exempt = {id(r) for r in cascaded or []}
    for r in readings:
        f = fields.get(r.field_name)
        if not f:
            errors[f"{r.field_name}#{r.repeat_num}"] = "unknown field for this visit"
            continue
        err = (None if id(r) in exempt else _completion_error(f, r)) or validate(f, r.value)
        if err:
            errors[f"{r.field_name}#{r.repeat_num}"] = err
    if not errors:
        errors.update(derive.check(fields, standing if standing is not None else readings,
                                   subj.birth_year if subj else None,
                                   subj.sex if subj else None, clock.today().year))
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
    if o.completion_status != "value":
        label = _COMPLETIONS.get(o.completion_status, (None, o.completion_status))[1]
        return f"{label}: {o.completion_reason}"
    if o.value_num is not None:
        return fmt_num(o.value_num)
    return o.value_text


def _after(num, text, completion: str, why: str | None) -> str | None:
    if completion != "value":
        return f"{_COMPLETIONS[completion][1]}: {why}"
    return fmt_num(num) if num is not None else text


def record_change(s: Session, o: Observation, num, text, by: str, reason: str | None,
                  completion: str = "value", why: str | None = None) -> ObservationHistory | None:
    """Write the history row, then change the value. Returns None when
    nothing changed, so an unchanged resubmission leaves no trace."""
    before, after = shown(o), _after(num, text, completion, why)
    if before == after:
        return None
    row = ObservationHistory(observation_id=o.id, old_value=before, new_value=after, changed_by=by, reason=reason)
    s.add(row)
    o.value_num, o.value_text = num, text
    o.completion_status, o.completion_reason = completion, why if completion != "value" else None
    o.updated_at = utcnow()
    return row


def _reopened_by_sponsor(s: Session, o: Observation) -> bool:
    """An approved value can change only while a person on the sponsor side has
    a query open on it. A site's own question or a system query does not count."""
    return s.scalars(select(Query.id).where(
        Query.observation_id == o.id, Query.status.in_(LIVE_QUERY),
        Query.raised_by_org == "sponsor", Query.raised_by != "system")).first() is not None


def open_query_counts(s: Session, ids: list[int]) -> dict[int, int]:
    rows = s.scalars(select(Query.observation_id).where(Query.observation_id.in_(ids), Query.status.in_(LIVE_QUERY)))
    out: dict[int, int] = {}
    for oid in rows:
        out[oid] = out.get(oid, 0) + 1
    return out


def _overlay(standing: list[Reading]) -> dict[tuple[str, int], tuple[object, str]]:
    return {(r.field_name, r.repeat_num): (r.value, r.completion_status) for r in standing}


MIN_REASON = 5


def save_readings(s: Session, cu: CurrentUser, p, v, subj: Subject, visit: str,
                  fields: dict[str, FieldDef], readings: list[Reading], reason: str | None = None) -> int:
    """The one path a value takes into the database, for data entry and for
    a correction through a query alike: same validation, same yes/no
    spelling, derived values recomputed, a history row for every change.

    New values are drafts. Changing one already submitted needs a reason and
    takes it back to submitted, so it is reviewed again. An approved value is
    frozen until the sponsor raises a query on it. A value that was recomputed
    follows its inputs whatever its status, and needs approving again too. Any
    change to a value in a signed visit undoes the sign-off."""
    scope.check_study_open(p)
    cascaded = _visit_not_performed(s, p, subj, visit, fields, readings)
    if cascaded:
        # Whatever the visit date's own reason says also explains these.
        why_date = next((r.completion_reason for r in readings if fields.get(r.field_name) is not None
                         and fields[r.field_name].cdash == VISIT_DATE_CODE), None)
        reason = reason or why_date
        readings = [*readings, *cascaded]
    rows, recomputed, standing = _prepare(s, p, subj, visit, fields, readings)
    check = _check(fields, [*readings, *recomputed], subj, standing, cascaded)
    if not check["ok"]:
        raise HTTPException(422, {"errors": check["errors"]})

    draft = DraftECRF.model_validate(v.content)
    checks.ensure(s, p, draft, v.version)
    given = {r.field_name for r in readings}
    names = {f.field_id: f.name for form in draft.forms for f in form.fields}
    hard = {f"{names.get(hit.field_id)}#{hit.repeat}": hit.message
            for _, hit in checks.failures(s, p, draft, subj, visit, _overlay(standing))
            if hit.severity == "hard" and names.get(hit.field_id) in given}
    if hard:
        raise HTTPException(422, {"errors": hard})

    def after(r: Reading):
        num, text = _split(fields[r.field_name], r.value) if r.completion_status == "value" else (None, None)
        return num, text, _after(num, text, r.completion_status, r.completion_reason)

    blocked, need_reason = [], []
    for r in readings:
        o = rows.get((r.field_name, r.repeat_num))
        if o is None or shown(o) == after(r)[2]:
            continue
        key = f"{r.field_name}#{r.repeat_num}"
        if o.status == "approved" and not _reopened_by_sponsor(s, o):
            blocked.append(key)
        elif o.status != "draft" and len((reason or "").strip()) < MIN_REASON:
            need_reason.append(key)
    if blocked:
        raise HTTPException(409, {"approved": blocked,
                                  "message": "These values have been approved by the sponsor and can "
                                             "no longer be changed here. Ask the sponsor to raise a query."})
    if need_reason:
        raise HTTPException(422, {"errors": dict.fromkeys(need_reason, f"Changing a submitted value needs a reason of at least {MIN_REASON} characters")})

    auto = {r.field_name for r in recomputed}
    reopened_submitted = False
    changes: list[ObservationHistory] = []
    for r in [*readings, *recomputed]:
        num, text, _ = after(r)
        o = rows.get((r.field_name, r.repeat_num))
        if o is None:
            if num is None and text is None and r.completion_status == "value":
                continue    # nothing typed, nothing to keep
            made = Observation(protocol_id=p.id, subject_id=subj.code, subject_ref=subj.id,
                               ecrf_version_id=v.id, visit=visit, field_name=r.field_name,
                               repeat_num=r.repeat_num, value_num=num, value_text=text,
                               completion_status=r.completion_status,
                               completion_reason=r.completion_reason if r.completion_status != "value" else None,
                               synthetic=True, status="draft", entered_by=cu.user.email)
            s.add(made)
            if r.completion_reason == VISIT_NOT_PERFORMED and any(r is c for c in cascaded):
                # A person did not type this one, so say where it came from.
                s.flush()
                s.add(ObservationHistory(observation_id=made.id, old_value=None, new_value=shown(made),
                                         changed_by=cu.user.email, reason=VISIT_NOT_PERFORMED))
            continue
        why = "recalculated after a change to its inputs" if r.field_name in auto else reason
        changed = record_change(s, o, num, text, cu.user.email, why, r.completion_status, r.completion_reason)
        if changed:
            changes.append(changed)
        if changed and o.status != "draft":
            o.status, o.approved_by, o.approved_at = "submitted", None, None
            reopened_submitted = True
    s.flush()
    if changes:
        signed = s.scalars(select(Signoff).where(Signoff.subject_ref == subj.id, Signoff.visit == visit,
                                                 Signoff.invalidated_at.is_(None))).first()
        if signed:
            signed.invalidated_at, signed.invalidated_by_history_id = utcnow(), changes[0].id
            notify.signoff_invalidated(s, p, subj.site_org_id, subj.code, visit)
    if reopened_submitted:
        _notify_raised(s, p, subj, visit, checks.sync_queries(s, p, draft, subj, visit))
    return len(readings)


def _notify_raised(s: Session, p, subj: Subject, visit: str, raised: list[Query]) -> None:
    for q in raised:
        notify.system_query(s, p, q, subj.code, visit)


def _warnings(s: Session, p, draft: DraftECRF, subj: Subject, visit: str, overlay=None) -> list[dict]:
    """What submitting would newly raise."""
    names = {f.field_id: f.name for form in draft.forms for f in form.fields}
    return [{"code": hit.code, "field": names.get(hit.field_id), "repeat": hit.repeat, "message": hit.message}
            for _, hit in checks.would_raise(s, p, draft, subj, visit, overlay)]


# ------------------------------------------------------------- site side

@router.post("/validate")
def validate_only(body: EntryRequest, cu: CurrentUser = Depends(require("data.enter")),
                  s: Session = Depends(db.get_session)):
    """Errors would stop the save. Warnings are what would become queries at
    submit. Nothing is written."""
    p, v, subj, fields = _locked_fields(s, cu, body)
    cascaded = _visit_not_performed(s, p, subj, body.visit, fields, body.readings)
    readings = [*body.readings, *cascaded]
    _, recomputed, standing = _prepare(s, p, subj, body.visit, fields, readings)
    result = _check(fields, [*readings, *recomputed], subj, standing, cascaded)
    draft = DraftECRF.model_validate(v.content)
    checks.ensure(s, p, draft, v.version)
    s.commit()
    result["warnings"] = _warnings(s, p, draft, subj, body.visit, _overlay(standing))
    return result


@router.post("/enter")
def enter(body: EntryRequest, cu: CurrentUser = Depends(require("data.enter")),
          s: Session = Depends(db.get_session)):
    p, v, subj, fields = _locked_fields(s, cu, body)
    saved = save_readings(s, cu, p, v, subj, body.visit, fields, body.readings, body.reason)
    s.commit()
    return {"saved": saved}


class SubmitRequest(BaseModel):
    protocol_id: int
    subject_id: str
    visit: str


@router.post("/submit")
def submit(body: SubmitRequest, cu: CurrentUser = Depends(require("data.submit")),
           s: Session = Depends(db.get_session)):
    """Run every check for the visit. A hard failure blocks; a soft one raises a
    system query. Then every draft value at this visit becomes submitted, and
    the sponsor can see it."""
    p, v, subj, _ = _locked_fields(s, cu, EntryRequest(protocol_id=body.protocol_id, subject_id=body.subject_id,
                                                       visit=body.visit, readings=[]))
    scope.check_study_open(p)
    draft = DraftECRF.model_validate(v.content)
    checks.ensure(s, p, draft, v.version)
    rows = list(s.scalars(select(Observation).where(Observation.protocol_id == p.id,
                                                    Observation.subject_id == subj.code,
                                                    Observation.visit == body.visit)))
    if not rows:
        raise HTTPException(422, "Nothing has been entered for this visit")
    names = {f.field_id: f.name for form in draft.forms for f in form.fields}
    hard = {f"{names.get(hit.field_id)}#{hit.repeat}": hit.message
            for _, hit in checks.failures(s, p, draft, subj, body.visit) if hit.severity == "hard"}
    if hard:
        raise HTTPException(422, {"errors": hard})
    moved = 0
    for o in rows:
        if o.status == "draft":
            o.status = "submitted"
            moved += 1
    s.flush()
    raised = checks.sync_queries(s, p, draft, subj, body.visit)
    _notify_raised(s, p, subj, body.visit, raised)
    if moved:
        notify.visit_submitted(s, p, subj.site_org_id, subj.code, body.visit)
    s.commit()
    return {"submitted": moved, "queries": [{"id": q.id, "code": q.check_code, "text": q.text} for q in raised]}


@router.post("/seed/{protocol_id}")
def seed(protocol_id: int, cu: CurrentUser = Depends(require("data.approve")),
         s: Session = Depends(db.get_session)):
    """Load synthetic observations for the dashboard demo, spread across
    the site organisations, all of them awaiting the sponsor's approval."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    scope.check_study_open(p)
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


def _row(s: Session, o: Observation, sites: dict[int, Organisation], queries: dict[int, int] | None = None) -> dict:
    subj = s.get(Subject, o.subject_ref) if o.subject_ref else None
    site = sites.get(subj.site_org_id) if subj else None
    return {
        "id": o.id, "site": site.code if site else None, "subject": o.subject_id,
        "visit": o.visit, "field": o.field_name, "repeat": o.repeat_num, "value": shown(o),
        "status": o.status, "open_query_count": (queries or {}).get(o.id, 0),
        "completion_status": o.completion_status, "completion_reason": o.completion_reason,
        "entered_by": o.entered_by, "entered_at": o.entered_at.isoformat(),
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
    found = list(s.scalars(q.order_by(Observation.subject_id, Observation.visit,
                                      Observation.field_name, Observation.repeat_num)))
    counts = open_query_counts(s, [o.id for o in found])
    rows = [_row(s, o, sites, counts) for o in found]
    if site:
        rows = [r for r in rows if r["site"] == site]
    return rows


@review_router.post("/{protocol_id}/data/approve")
def approve_data(protocol_id: int, body: ApproveRequest,
                 cu: CurrentUser = Depends(require("data.approve")),
                 s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    scope.check_study_open(p)
    rows = s.scalars(select(Observation).where(Observation.protocol_id == protocol_id, Observation.status != "draft",
                                                Observation.id.in_(body.observation_ids))).all()
    live = open_query_counts(s, list(body.observation_ids))
    blocked = [o.id for o in rows if o.id in live and o.status != "approved"]
    if blocked:
        raise HTTPException(409, {"queried": blocked,
                                  "message": "Close the open queries on these values before approving them"})
    if p.monitor_review_required:
        unreviewed = [o.id for o in rows if o.status == "submitted"]
        if unreviewed:
            raise HTTPException(409, {"unreviewed": unreviewed,
                                      "message": "This study needs monitor review before approval"})
    now = utcnow()
    touched = set()
    for o in rows:
        if o.status != "approved":
            o.status, o.approved_by, o.approved_at = "approved", cu.user.email, now
            touched.add((o.subject_ref, o.subject_id, o.visit))
    s.flush()
    for ref, code, visit in touched:
        statuses = s.scalars(select(Observation.status).where(Observation.protocol_id == protocol_id,
                                                              Observation.subject_ref == ref,
                                                              Observation.visit == visit)).all()
        if ref and all(st == "approved" for st in statuses):
            site_id = s.get(Subject, ref).site_org_id
            notify.visit_approved(s, p, site_id, code, visit)
            if p.investigator_signature_required:
                notify.signoff_needed(s, p, site_id, code, visit)
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


