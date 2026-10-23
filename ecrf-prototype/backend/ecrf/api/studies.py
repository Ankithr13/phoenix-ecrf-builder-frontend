"""The site portal: studies a site has been assigned, and its patients.

A study is visible only when the sponsor has locked the form and assigned
the site; both conditions live in scope.visible_protocols."""

from fastapi import APIRouter, Depends
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
            "created_at": subj.created_at.isoformat(), "readings": entered}


@router.get("/{protocol_id}/subjects")
def list_subjects(protocol_id: int, cu: CurrentUser = Depends(require("study.view", "data.view")),
                  s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    rows = s.scalars(scope.visible_subjects(cu, protocol_id).order_by(Subject.code)).all()
    return [_subject_row(s, r) for r in rows]


@router.post("/{protocol_id}/subjects")
def create_subject(protocol_id: int, cu: CurrentUser = Depends(require("subject.create")),
                   s: Session = Depends(db.get_session)):
    """The server makes the code, {SITECODE}-{nnn}, so the client never
    types a patient id and cannot claim another site's patient."""
    scope.protocol_or_404(s, cu, protocol_id)
    n = s.scalar(select(func.count(Subject.id)).where(
        Subject.protocol_id == protocol_id, Subject.site_org_id == cu.org.id)) or 0
    code = f"{cu.org.code}-{n + 1:03d}"
    while s.scalars(select(Subject).where(Subject.protocol_id == protocol_id, Subject.code == code)).first():
        n += 1
        code = f"{cu.org.code}-{n + 1:03d}"
    subj = Subject(protocol_id=protocol_id, site_org_id=cu.org.id, code=code, created_by=cu.user.email)
    s.add(subj)
    s.commit()
    return _subject_row(s, subj)
