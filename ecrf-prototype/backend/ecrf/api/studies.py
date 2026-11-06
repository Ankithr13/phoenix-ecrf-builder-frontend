"""The site portal: studies a site has been assigned, and its patients.

A study is visible only when the sponsor has locked the form and assigned
the site; both conditions live in scope.visible_protocols."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import DATA_READERS, CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import (
    LIVE_QUERY,
    Observation,
    Organisation,
    Protocol,
    Query,
    Signoff,
    Subject,
)

router = APIRouter(prefix="/api/studies", tags=["studies"])


@router.get("")
def list_studies(cu: CurrentUser = Depends(require("protocol.view")),
                 s: Session = Depends(db.get_session)):
    scope.require_site_side(cu)
    out = []
    for p in s.scalars(scope.visible_protocols(cu)).all():
        v = db.locked_version(s, p.id)
        n = s.scalar(select(func.count(Subject.id)).where(
            Subject.protocol_id == p.id, Subject.site_org_id == cu.org.id)) or 0
        out.append({"id": p.id, "name": p.name, "pages": p.pages,
                    "locked_at": v.locked_at.isoformat() if v and v.locked_at else None,
                    "visits": [f["visit"] for f in (v.content.get("forms", []) if v else [])],
                    "subjects": n})
    return out


def _subject_row(s: Session, subj: Subject, rows: list[Observation] | None = None, open_queries: int = 0,
                 p: Protocol | None = None) -> dict:
    site = s.get(Organisation, subj.site_org_id)
    rows = rows or []
    signoffs = list(s.scalars(select(Signoff).where(Signoff.subject_ref == subj.id)))
    needs, resign = _signoff_state(rows, signoffs) if (p is None or p.investigator_signature_required) else ([], [])
    return {"id": subj.id, "code": subj.code, "site": site.code if site else None,
            "site_name": site.name if site else None, "created_by": subj.created_by,
            "created_at": subj.created_at.isoformat(), "readings": len(rows),
            "birth_year": subj.birth_year, "sex": subj.sex,
            "enrolled_on": subj.enrolled_on, "note": subj.note,
            "statuses": sorted({o.status for o in rows}), "open_queries": open_queries,
            "needs_signoff": bool(needs), "needs_resign": resign}


def _signoff_state(rows: list[Observation], signoffs: list[Signoff]) -> tuple[list[str], list[str]]:
    """Visits whose values are all approved and which have no valid sign-off,
    and of those, the ones that had one until a value changed."""
    visits: dict[str, list[str]] = {}
    for o in rows:
        visits.setdefault(o.visit, []).append(o.status)
    valid = {x.visit for x in signoffs if x.invalidated_at is None}
    undone = {x.visit for x in signoffs if x.invalidated_at is not None}
    needs = [v for v, statuses in visits.items() if v not in valid and all(st == "approved" for st in statuses)]
    return needs, sorted(v for v in undone if v not in valid)


SEXES = ("Female", "Male", "Other", "Unknown")


class SubjectCreate(BaseModel):
    """Everything optional: an empty body still registers a patient. The code
    always comes from the server. Anything else is refused rather than
    ignored, so a name or initials cannot slip in through an extra key."""
    model_config = ConfigDict(extra="forbid")

    birth_year: int | None = None
    sex: str | None = None
    enrolled_on: str | None = None   # YYYY-MM-DD
    note: str | None = None


def _clean(body: SubjectCreate) -> dict:
    out: dict = {}
    if body.birth_year is not None:
        if not 1900 <= body.birth_year <= date.today().year:
            raise HTTPException(422, f"Year of birth must be between 1900 and {date.today().year}")
        out["birth_year"] = body.birth_year
    if body.sex:
        if body.sex not in SEXES:
            raise HTTPException(422, f"Sex must be one of {', '.join(SEXES)}")
        out["sex"] = body.sex
    if body.enrolled_on:
        try:
            d = date.fromisoformat(body.enrolled_on)
        except ValueError as e:
            raise HTTPException(422, "Enrolment date must be YYYY-MM-DD") from e
        if d > date.today():
            raise HTTPException(422, "Enrolment date cannot be in the future")
        out["enrolled_on"] = d.isoformat()
    if body.note and body.note.strip():
        out["note"] = body.note.strip()[:500]
    return out


@router.get("/{protocol_id}/subjects")
def list_subjects(protocol_id: int, visit: str | None = None, status: str | None = None,
                  open_queries: bool = False, needs_signoff: bool = False,
                  cu: CurrentUser = Depends(require(*DATA_READERS)),
                  s: Session = Depends(db.get_session)):
    """Filters: patients with a value at this visit and in this status, with an
    open query, or with a visit ready for sign-off."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    by_subject: dict[int, list[Observation]] = {}
    for o in s.scalars(scope.visible_observations(cu, protocol_id)):
        by_subject.setdefault(o.subject_ref, []).append(o)
    live: dict[int, int] = {}
    for ref in s.scalars(select(Query.subject_ref).where(Query.protocol_id == protocol_id, Query.status.in_(LIVE_QUERY))):
        live[ref] = live.get(ref, 0) + 1
    out = []
    for subj in s.scalars(scope.visible_subjects(cu, protocol_id).order_by(Subject.code)):
        rows = by_subject.get(subj.id, [])
        at_visit = [o for o in rows if not visit or o.visit == visit]
        if (visit or status) and not any(not status or o.status == status for o in at_visit):
            continue
        if open_queries and not live.get(subj.id):
            continue
        row = _subject_row(s, subj, rows, live.get(subj.id, 0), p)
        if needs_signoff and not row["needs_signoff"]:
            continue
        out.append(row)
    return out


@router.post("/{protocol_id}/subjects")
def create_subject(protocol_id: int, body: SubjectCreate | None = None,
                   cu: CurrentUser = Depends(require("subject.create")),
                   s: Session = Depends(db.get_session)):
    """Register a patient. The code is {SITECODE}-{nnn}, always made by the
    server, so a site can never claim another site's patient and a name can
    never become an identifier."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    scope.check_study_open(p)
    fields = _clean(body or SubjectCreate())
    n = s.scalar(select(func.count(Subject.id)).where(
        Subject.protocol_id == protocol_id, Subject.site_org_id == cu.org.id)) or 0
    code = f"{cu.org.code}-{n + 1:03d}"
    while s.scalars(select(Subject).where(Subject.protocol_id == protocol_id, Subject.code == code)).first():
        n += 1
        code = f"{cu.org.code}-{n + 1:03d}"
    subj = Subject(protocol_id=protocol_id, site_org_id=cu.org.id, code=code,
                   created_by=cu.user.email, **fields)
    s.add(subj)
    s.commit()
    return _subject_row(s, subj)
