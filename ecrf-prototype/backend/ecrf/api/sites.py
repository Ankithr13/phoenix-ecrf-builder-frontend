"""Which sites work on a protocol. Assignment needs a locked form, because
a site only ever sees the locked version."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import Organisation, ProtocolSite

router = APIRouter(prefix="/api/protocols", tags=["sites"])


class SiteRef(BaseModel):
    site_org_id: int


@router.get("/{protocol_id}/sites")
def list_sites(protocol_id: int, cu: CurrentUser = Depends(require("protocol.view")),
               s: Session = Depends(db.get_session)):
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
def assign(protocol_id: int, body: SiteRef, cu: CurrentUser = Depends(require("site.assign")),
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
def unassign(protocol_id: int, site_org_id: int, cu: CurrentUser = Depends(require("site.assign")),
             s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    row = s.scalars(select(ProtocolSite).where(ProtocolSite.protocol_id == protocol_id,
                                                ProtocolSite.site_org_id == site_org_id)).first()
    if row:
        s.delete(row)
        s.commit()
    return {"assigned": False}
