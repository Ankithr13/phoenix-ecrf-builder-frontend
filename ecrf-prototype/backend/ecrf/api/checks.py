"""The edit checks on a protocol, read only.

The built-in checks are generated when the form is locked (checks/builtin.py)
and run on submit (checks/run.py). Custom checks are not offered in this
version, so there is nothing here to add, edit, switch off or try out."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import EditCheck

router = APIRouter(prefix="/api/protocols", tags=["edit checks"])


def _row(c: EditCheck) -> dict:
    return {"id": c.id, "code": c.code, "form": c.form, "field_ids": c.field_ids, "type": c.type, "logic": c.logic,
            "message": c.message, "severity": c.severity, "owner": c.owner, "enabled": c.enabled, "origin": c.origin,
            "form_version": c.form_version}


@router.get("/{protocol_id}/checks")
def list_checks(protocol_id: int, cu: CurrentUser = Depends(require("protocol.view")),
                s: Session = Depends(db.get_session)):
    scope.require_sponsor_side(cu)
    scope.protocol_or_404(s, cu, protocol_id)
    rows = s.scalars(select(EditCheck).where(EditCheck.protocol_id == protocol_id).order_by(EditCheck.code, EditCheck.id))
    return [_row(c) for c in rows]
