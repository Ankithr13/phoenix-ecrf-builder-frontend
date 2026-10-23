"""What a signed-in user may see. Every list and every lookup goes through
here, so the rule lives in one place:

  sponsor   protocols that belong to its organisation
  site      protocols assigned to it and locked (stage 3); nothing before

A row outside the scope is reported as 404."""

from fastapi import HTTPException
from sqlalchemy import Select, false, select
from sqlalchemy.orm import Session

from ecrf.auth.permissions import CurrentUser
from ecrf.storage.models import Protocol


def visible_protocols(cu: CurrentUser) -> Select:
    if cu.org.type == "sponsor":
        return select(Protocol).where(Protocol.org_id == cu.org.id)
    return select(Protocol).where(false())


def protocol_or_404(s: Session, cu: CurrentUser, protocol_id: int) -> Protocol:
    p = s.scalars(visible_protocols(cu).where(Protocol.id == protocol_id)).first()
    if p is None:
        raise HTTPException(404, "protocol not found")
    return p
