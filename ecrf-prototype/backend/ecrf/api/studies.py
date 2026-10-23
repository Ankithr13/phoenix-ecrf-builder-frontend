"""The site portal's view of the world: studies it has been assigned.

Stage 2 ships the endpoint with its permission and scope in place; the
assignment table arrives in stage 3, until then a site sees no studies."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db

router = APIRouter(prefix="/api/studies", tags=["studies"])


@router.get("")
def list_studies(cu: CurrentUser = Depends(require("study.view")),
                 s: Session = Depends(db.get_session)):
    rows = s.scalars(scope.visible_protocols(cu)).all()
    return [{"id": p.id, "name": p.name, "pages": p.pages} for p in rows]
