"""The site portal: studies a site has been assigned, and its patients.

A study is visible only when the sponsor has locked the form and assigned
the site; both conditions live in scope.visible_protocols."""

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import Observation, Organisation, Subject

router = APIRouter(prefix="/api/studies", tags=["studies"])


@router.get("")
def list_studies(cu: CurrentUser = Depends(require("study.view")),
                 s: Session = Depends(db.get_session)):
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


def _subject_row(s: Session, subj: Subject) -> dict:
    site = s.get(Organisation, subj.site_org_id)
    entered = s.scalar(select(func.count(Observation.id)).where(Observation.subject_ref == subj.id)) or 0
    return {"id": subj.id, "code": subj.code, "site": site.code if site else None,
            "site_name": site.name if site else None, "created_by": subj.created_by,
            "created_at": subj.created_at.isoformat(), "readings": entered,
            "initials": subj.initials, "birth_year": subj.birth_year, "sex": subj.sex,
            "enrolled_on": subj.enrolled_on, "note": subj.note}


SEXES = ("Female", "Male", "Other", "Unknown")


class SubjectCreate(BaseModel):
    """Everything optional: an empty body still registers a patient with a
    server-made code. No name and no full date of birth, on purpose."""
    code: str | None = None
    initials: str | None = None
    birth_year: int | None = None
    sex: str | None = None
    enrolled_on: str | None = None   # YYYY-MM-DD
    note: str | None = None


def _clean(body: SubjectCreate, site_code: str) -> dict:
    out: dict = {}
    code = (body.code or "").strip().upper()
    if code:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{0,49}", code):
            raise HTTPException(422, "Subject ID may contain letters, digits and hyphens only")
        if not code.startswith(f"{site_code}-"):
            raise HTTPException(422, f"Subject IDs at this site must start with {site_code}-")
        out["code"] = code
    initials = (body.initials or "").strip().upper()
    if initials:
        if not re.fullmatch(r"[A-Z]{2,4}", initials):
            raise HTTPException(422, "Initials are 2 to 4 letters")
        out["initials"] = initials
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
def list_subjects(protocol_id: int, cu: CurrentUser = Depends(require("study.view", "data.view")),
                  s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    rows = s.scalars(scope.visible_subjects(cu, protocol_id).order_by(Subject.code)).all()
    return [_subject_row(s, r) for r in rows]


@router.post("/{protocol_id}/subjects")
def create_subject(protocol_id: int, body: SubjectCreate | None = None,
                   cu: CurrentUser = Depends(require("subject.create")),
                   s: Session = Depends(db.get_session)):
    """Register a patient. The code is {SITECODE}-{nnn} made by the server
    unless the site supplies one, which must carry the site's own prefix so
    a site can never claim another site's patient."""
    scope.protocol_or_404(s, cu, protocol_id)
    fields = _clean(body or SubjectCreate(), cu.org.code)
    code = fields.pop("code", None)
    if code:
        if s.scalars(select(Subject).where(Subject.protocol_id == protocol_id, Subject.code == code)).first():
            raise HTTPException(409, f"{code} is already registered on this study")
    else:
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
