"""The statistical analysis plan page: which field, which visits, which rule.

The columns follow the client's traceability matrix. A row chooses what the
fixed calculations in stats/registry.py work on, and can add no calculation of
its own. Each change writes form_field_history."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.schema import DraftECRF
from ecrf.stats.calculations import _OPS as RULE_OPS
from ecrf.stats.registry import KINDS
from ecrf.storage import db
from ecrf.storage.models import FormFieldHistory, Protocol, SapItem

router = APIRouter(prefix="/api/protocols", tags=["statistical analysis plan"])

NUMERIC = ("integer", "decimal")


def _row(i: SapItem, names: dict[str, str]) -> dict:
    return {"id": i.id, "label": i.label, "kind": i.kind, "field_id": i.field_id, "field": names.get(i.field_id),
            "baseline_visit_id": i.baseline_visit_id, "analysis_visit_id": i.analysis_visit_id, "unit": i.unit,
            "responder_rule": i.responder_rule, "method": i.method}


def _form(s: Session, protocol_id: int) -> tuple[DraftECRF, int]:
    v = db.latest_version(s, protocol_id)
    if v is None:
        raise HTTPException(409, "Extract the form first; the plan points at its fields")
    return DraftECRF.model_validate(v.content), v.version


def _names(draft: DraftECRF) -> dict[str, str]:
    return {f.field_id: f.name for form in draft.forms for f in form.fields}


class SapIn(BaseModel):
    label: str
    kind: str
    field_id: str
    baseline_visit_id: str | None = None
    analysis_visit_id: str | None = None
    unit: str | None = None
    responder_rule: dict | None = None
    method: str | None = None


def _validate(body: SapIn, draft: DraftECRF) -> None:
    if not body.label.strip():
        raise HTTPException(422, "A row needs a label")
    if body.kind not in KINDS:
        raise HTTPException(422, f"Kind must be one of: {', '.join(KINDS)}")
    placed = [(form.visit, f) for form in draft.forms for f in form.fields]
    field = next((f for _, f in placed if f.field_id == body.field_id), None)
    if field is None:
        raise HTTPException(422, "That field is not on this form")
    has = {visit for visit, f in placed if f.name == field.name}
    for visit in (body.baseline_visit_id, body.analysis_visit_id):
        if visit and body.kind != "safety" and visit not in has:
            raise HTTPException(422, f"{field.name} is not collected at {visit}")
    if body.kind == "endpoint":
        if field.type not in NUMERIC:
            raise HTTPException(422, "An endpoint needs a numeric field")
        if not body.baseline_visit_id or not body.analysis_visit_id:
            raise HTTPException(422, "An endpoint needs a baseline visit and an analysis visit")
        if body.baseline_visit_id == body.analysis_visit_id:
            raise HTTPException(422, "The baseline and analysis visits must differ")
    if body.kind == "safety" and field.type != "date":
        raise HTTPException(422, "A safety item points at the adverse event's start date field")
    if body.kind == "baseline" and not body.baseline_visit_id:
        raise HTTPException(422, "A baseline item needs a baseline visit")
    if body.kind == "disposition" and not body.analysis_visit_id:
        raise HTTPException(422, "A disposition item needs an analysis visit")
    rule = body.responder_rule
    if rule is not None:
        if body.kind != "endpoint":
            raise HTTPException(422, "Only an endpoint can have a responder rule")
        if (rule.get("on") not in ("change", "analysis") or rule.get("op") not in RULE_OPS
                or not isinstance(rule.get("value"), int | float) or isinstance(rule.get("value"), bool)):
            raise HTTPException(422, "A responder rule is: on change or analysis, an operator, and a number")


def _log(s: Session, cu: CurrentUser, p: Protocol, version: int, item: SapItem, old: dict | None, new: dict | None) -> None:
    def text(v):
        return json.dumps(v)[:1000] if v is not None else None
    s.add(FormFieldHistory(protocol_id=p.id, version=version, field_id=item.field_id, attribute=f"sap_item:{item.id}",
                           old_value=text(old), new_value=text(new), by=cu.user.email))


def _item(s: Session, protocol_id: int, item_id: int) -> SapItem:
    i = s.get(SapItem, item_id)
    if i is None or i.protocol_id != protocol_id:
        raise HTTPException(404, "row not found")
    return i


@router.get("/{protocol_id}/sap")
def list_items(protocol_id: int, cu: CurrentUser = Depends(require("dashboard.view")),
               s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    draft, _ = _form(s, protocol_id)
    names = _names(draft)
    rows = s.scalars(select(SapItem).where(SapItem.protocol_id == protocol_id).order_by(SapItem.id))
    return {"items": [_row(i, names) for i in rows], "kinds": list(KINDS),
            "operators": list(RULE_OPS), "visits": list(dict.fromkeys(f.visit for f in draft.forms)),
            "fields": [{"field_id": f.field_id, "name": f.name, "visit": form.visit, "type": f.type, "unit": f.unit}
                       for form in draft.forms for f in form.fields]}


@router.post("/{protocol_id}/sap")
def add_item(protocol_id: int, body: SapIn, cu: CurrentUser = Depends(require("sap.edit")),
             s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    scope.check_study_open(p)
    draft, version = _form(s, protocol_id)
    _validate(body, draft)
    i = SapItem(protocol_id=protocol_id, **{**body.model_dump(), "label": body.label.strip()})
    s.add(i)
    s.flush()
    names = _names(draft)
    _log(s, cu, p, version, i, None, _row(i, names))
    s.commit()
    return _row(i, names)


@router.put("/{protocol_id}/sap/{item_id}")
def edit_item(protocol_id: int, item_id: int, body: SapIn, cu: CurrentUser = Depends(require("sap.edit")),
              s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    scope.check_study_open(p)
    i = _item(s, protocol_id, item_id)
    draft, version = _form(s, protocol_id)
    _validate(body, draft)
    names = _names(draft)
    before = _row(i, names)
    for key, value in {**body.model_dump(), "label": body.label.strip()}.items():
        setattr(i, key, value)
    _log(s, cu, p, version, i, before, _row(i, names))
    s.commit()
    return _row(i, names)


@router.delete("/{protocol_id}/sap/{item_id}")
def delete_item(protocol_id: int, item_id: int, cu: CurrentUser = Depends(require("sap.edit")),
                s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    scope.check_study_open(p)
    i = _item(s, protocol_id, item_id)
    draft, version = _form(s, protocol_id)
    _log(s, cu, p, version, i, _row(i, _names(draft)), None)
    s.delete(i)
    s.commit()
    return {"deleted": item_id}
