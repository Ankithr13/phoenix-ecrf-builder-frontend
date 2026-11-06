"""Which sites work on a protocol. Assignment needs a locked form, because
a site only ever sees the locked version."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import Observation, Organisation, ProtocolSite, Subject

router = APIRouter(prefix="/api/protocols", tags=["sites"])


class SiteRef(BaseModel):
    site_org_id: int


@router.get("/{protocol_id}/sites")
def list_sites(protocol_id: int, cu: CurrentUser = Depends(require("protocol.view")),
               s: Session = Depends(db.get_session)):
    scope.require_sponsor_side(cu)
    scope.protocol_or_404(s, cu, protocol_id)
    assigned = {r.site_org_id for r in s.scalars(
        select(ProtocolSite).where(ProtocolSite.protocol_id == protocol_id))}
    sites = s.scalars(select(Organisation).where(Organisation.type == "site")
                      .order_by(Organisation.code)).all()
    return [{"org_id": o.id, "name": o.name, "code": o.code, "assigned": o.id in assigned}
            for o in sites]


def _locked_or_409(s: Session, protocol_id: int) -> None:
    if db.locked_version(s, protocol_id) is None:
        raise HTTPException(409, "Lock the form before assigning sites; a site only ever sees a locked form")


@router.post("/{protocol_id}/sites")
def assign(protocol_id: int, body: SiteRef, cu: CurrentUser = Depends(require("sites.assign")),
           s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    _locked_or_409(s, protocol_id)
    org = s.get(Organisation, body.site_org_id)
    if org is None or org.type != "site":
        raise HTTPException(404, "site not found")
    if not s.scalars(select(ProtocolSite).where(ProtocolSite.protocol_id == protocol_id,
                                                 ProtocolSite.site_org_id == org.id)).first():
        s.add(ProtocolSite(protocol_id=protocol_id, site_org_id=org.id, assigned_by=cu.user.email))
        s.commit()
    return {"assigned": True, "site": org.code}


@router.delete("/{protocol_id}/sites/{site_org_id}")
def unassign(protocol_id: int, site_org_id: int, force: bool = False,
             cu: CurrentUser = Depends(require("sites.assign")),
             s: Session = Depends(db.get_session)):
    """A site with patients or data loses sight of them when unassigned, so
    that takes force=true. The rows stay either way."""
    scope.protocol_or_404(s, cu, protocol_id)
    subjects = s.scalar(select(func.count(Subject.id)).where(
        Subject.protocol_id == protocol_id, Subject.site_org_id == site_org_id)) or 0
    rows = s.scalar(select(func.count(Observation.id)).join(Subject, Subject.id == Observation.subject_ref).where(
        Observation.protocol_id == protocol_id, Subject.site_org_id == site_org_id)) or 0
    if (subjects or rows) and not force:
        raise HTTPException(409, {
            "count": rows, "subjects": subjects,
            "message": f"This site has {subjects} patient(s) and {rows} value(s) on this study. They "
                       f"stay in the database, but the site will no longer see them. Add ?force=true "
                       f"to unassign anyway."})
    row = s.scalars(select(ProtocolSite).where(ProtocolSite.protocol_id == protocol_id,
                                                ProtocolSite.site_org_id == site_org_id)).first()
    if row:
        s.delete(row)
        s.commit()
    return {"assigned": False}
