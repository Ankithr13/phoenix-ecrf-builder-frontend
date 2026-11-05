from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db

router = APIRouter(prefix="/api/navigation", tags=["navigation"])


@router.get("/protocols/{protocol_id}")
def protocol_context(protocol_id: int, subject: str | None = None,
                     current: CurrentUser = Depends(require("protocol.view", "study.view")),
                     session: Session = Depends(db.get_session)):
    protocol = scope.protocol_or_404(session, current, protocol_id)
    patient = scope.subject_or_404(session, current, protocol.id, subject) if subject is not None else None
    study = db.protocol_study(session, protocol.id)
    version = db.latest_version(session, protocol.id)
    return {
        "protocol": {"id": protocol.id, "name": protocol.name, "state": version.state if version else None},
        "study": {"id": study.id, "name": study.name, "code": study.code}
        if study and study.org_id == protocol.org_id else None,
        "subject": {"code": patient.code} if patient else None,
    }
