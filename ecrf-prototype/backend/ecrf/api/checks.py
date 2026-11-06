"""The edit checks for a protocol: list, add, switch on and off, try one out.

Before the form is locked a builder manages them. After the lock a change can
affect data already entered, so it takes the data manager and writes
form_field_history."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.checks import engine, run
from ecrf.schema import DraftECRF
from ecrf.storage import db
from ecrf.storage.models import EditCheck, FormFieldHistory, Protocol

router = APIRouter(prefix="/api/protocols", tags=["edit checks"])

CUSTOM_TYPES = ("required", "range", "format", "cross_field", "cross_form", "temporal", "conditional", "manual")


def _row(c: EditCheck) -> dict:
    return {"id": c.id, "code": c.code, "form": c.form, "field_ids": c.field_ids, "type": c.type, "logic": c.logic,
            "message": c.message, "severity": c.severity, "owner": c.owner, "enabled": c.enabled, "origin": c.origin,
            "form_version": c.form_version}


def _draft(s: Session, protocol_id: int) -> tuple[DraftECRF, bool, int]:
    v = db.latest_version(s, protocol_id)
    if v is None:
        raise HTTPException(409, "Extract the form first; checks are about its fields")
    return DraftECRF.model_validate(v.content), v.state == "locked", v.version


def _may_change(cu: CurrentUser, locked: bool) -> None:
    if locked and not cu.can("protocol.lock"):
        raise HTTPException(403, "After the form is locked, only a data manager can change its checks")
    if not locked and not cu.can("form.edit"):
        raise HTTPException(403, "Before the form is locked, a builder manages its checks")


def _log(s: Session, cu: CurrentUser, p: Protocol, version: int, code: str, old, new, reason: str | None = None) -> None:
    s.add(FormFieldHistory(protocol_id=p.id, version=version, field_id=None, attribute=f"edit_check:{code}",
                           old_value=old, new_value=new, by=cu.user.email, reason=reason))


class CheckIn(BaseModel):
    type: str
    field_ids: list[str]
    message: str
    logic: dict = {}
    form: str | None = None
    severity: str = "soft"


def _validate(body: CheckIn, draft: DraftECRF) -> None:
    if body.type not in CUSTOM_TYPES:
        raise HTTPException(422, f"Check type must be one of: {', '.join(CUSTOM_TYPES)}")
    if not body.message.strip():
        raise HTTPException(422, "A check needs the message the site will see")
    if body.severity not in ("soft", "hard"):
        raise HTTPException(422, "Severity is soft or hard")
    if body.severity == "hard" and body.type != "format":
        raise HTTPException(422, "Only format checks can be hard; everything else raises a query")
    known = {f.field_id for form in draft.forms for f in form.fields}
    unknown = [f for f in body.field_ids if f not in known]
    if unknown or not body.field_ids:
        raise HTTPException(422, "A check needs at least one field on this form")
    for key in ("a", "b", "if_field"):
        if key in body.logic and body.logic[key] not in known:
            raise HTTPException(422, f"Unknown field in logic: {key}")


@router.get("/{protocol_id}/checks")
def list_checks(protocol_id: int, cu: CurrentUser = Depends(require("protocol.view")),
                s: Session = Depends(db.get_session)):
    scope.require_sponsor_side(cu)
    scope.protocol_or_404(s, cu, protocol_id)
    rows = s.scalars(select(EditCheck).where(EditCheck.protocol_id == protocol_id).order_by(EditCheck.code, EditCheck.id))
    return [_row(c) for c in rows]


@router.post("/{protocol_id}/checks")
def add_check(protocol_id: int, body: CheckIn, cu: CurrentUser = Depends(require("form.edit", "protocol.lock")),
              s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    draft, locked, version = _draft(s, protocol_id)
    _may_change(cu, locked)
    _validate(body, draft)
    n = s.scalar(select(func.count(EditCheck.id)).where(EditCheck.protocol_id == protocol_id,
                                                        EditCheck.origin == "custom")) or 0
    c = EditCheck(protocol_id=protocol_id, code=f"CUSTOM-{n + 1}", form=body.form, field_ids=body.field_ids,
                  type=body.type, logic=body.logic, message=body.message.strip(), severity=body.severity,
                  owner=cu.user.email, origin="custom", form_version=version)
    s.add(c)
    s.flush()
    if locked:
        _log(s, cu, p, version, c.code, None, f"added: {c.type}, {c.severity}")
    s.commit()
    return _row(c)


class CheckEdit(BaseModel):
    enabled: bool | None = None
    message: str | None = None
    reason: str | None = None


@router.patch("/{protocol_id}/checks/{check_id}")
def edit_check(protocol_id: int, check_id: int, body: CheckEdit,
               cu: CurrentUser = Depends(require("form.edit", "protocol.lock")),
               s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    _, locked, version = _draft(s, protocol_id)
    _may_change(cu, locked)
    c = s.get(EditCheck, check_id)
    if c is None or c.protocol_id != protocol_id:
        raise HTTPException(404, "check not found")
    if body.enabled is not None and body.enabled != c.enabled:
        if c.origin == "builtin" and c.type == "format" and not body.enabled:
            raise HTTPException(422, "A built-in format check follows from the field's type and stays on")
        if locked:
            _log(s, cu, p, version, c.code, f"enabled={c.enabled}", f"enabled={body.enabled}", body.reason)
        c.enabled = body.enabled
    if body.message is not None and body.message.strip() and body.message.strip() != c.message:
        if locked:
            _log(s, cu, p, version, c.code, c.message, body.message.strip(), body.reason)
        c.message = body.message.strip()
    s.commit()
    return _row(c)


class CheckTest(BaseModel):
    type: str
    field_ids: list[str]
    logic: dict = {}
    sample: dict[str, str | float | int | None] = {}


class _Probe:
    code = "TEST"
    message = "fails"
    severity = "soft"

    def __init__(self, body: CheckTest):
        self.type, self.field_ids, self.logic = body.type, body.field_ids, body.logic


@router.post("/{protocol_id}/checks/test")
def try_check(protocol_id: int, body: CheckTest, cu: CurrentUser = Depends(require("form.edit", "protocol.lock")),
              s: Session = Depends(db.get_session)):
    """Try logic against sample values without saving anything."""
    scope.protocol_or_404(s, cu, protocol_id)
    draft, _, _ = _draft(s, protocol_id)
    ctx = run.context_from(draft, {})
    for field_id, value in body.sample.items():
        ctx.answers[field_id] = [engine.Answer(value)]
    if body.type == "manual":
        return {"passes": None, "note": "A manual check is listed for people to do. It is never evaluated."}
    return {"passes": engine.evaluate(_Probe(body), ctx) is None}
