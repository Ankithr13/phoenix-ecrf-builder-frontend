"""The results on the Dashboard: which field, which visits, which calculation.

Each row is a sap_item. The data manager adds one by picking a field, a before
visit, an after visit and a calculation, and the server fills in the rest: the
SAP item, form, unit, endpoint or concept, derivation and method. A row only
chooses what the fixed calculations in stats/registry.py work on, and can add
no calculation of its own. Each change writes form_field_history.

The traceability matrix is generated from the same rows, in the eight columns
of the client's eCRF-to-SAP guide."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.schema import DraftECRF, FieldDef
from ecrf.stats.calculations import _OPS as RULE_OPS
from ecrf.stats.registry import CALCULATIONS, CATEGORICAL, KINDS, NUMERIC, derivation
from ecrf.storage import db
from ecrf.storage.models import FormFieldHistory, Protocol, SapItem

router = APIRouter(prefix="/api/protocols", tags=["results"])

# What the data manager picks, and the kind of row each one is stored as. The
# kind is what the registry and the independent verifier read, so they are
# unchanged. Missing values come with every row and are not a choice.
CHOICES: dict[str, dict] = {
    "descriptive": {"label": "Descriptive statistics", "types": NUMERIC, "method": "Descriptive statistics: n, mean, SD, median, min, max"},
    "frequency": {"label": "Frequency", "types": CATEGORICAL, "method": "Counts and percentages"},
    "change_from_baseline": {"label": "Change from baseline", "types": NUMERIC, "method": "Paired t-test, 95% CI"},
    "responder_rate": {"label": "Responder rate", "types": NUMERIC, "method": "Responder rate, Wilson 95% CI"},
    "teae_count": {"label": "Treatment-emergent adverse events", "types": ("date",), "method": "Subject count and percent"},
}

# The client's eCRF-to-SAP guide, section 3, in its order.
MATRIX_COLUMNS = ["SAP Item", "Endpoint / Concept", "eCRF Form", "eCRF Field(s)", "Visit / Window", "Unit",
                  "Analysis Derivation", "SAP Method"]

_KIND_LABEL = {"endpoint": "Endpoint", "baseline": "Baseline", "disposition": "Disposition", "safety": "Safety"}


def calculation_of(kind: str, rule: dict | None, field_type: str | None) -> str | None:
    """The choice a stored row stands for, so Edit can show it again."""
    if kind == "endpoint":
        return "responder_rate" if rule else "change_from_baseline"
    if kind == "safety":
        return "teae_count"
    if field_type in NUMERIC:
        return "descriptive"
    if field_type in CATEGORICAL:
        return "frequency"
    return None


def _kind_for(calc: str, before: str | None, after: str | None) -> str:
    if calc in ("change_from_baseline", "responder_rate"):
        return "endpoint"
    if calc == "teae_count":
        return "safety"
    if before and after:
        raise HTTPException(422, "A summary is at one visit: pick the before visit or the after visit, not both")
    if not before and not after:
        raise HTTPException(422, "Pick the visit to summarise")
    return "baseline" if before else "disposition"


def rule_text(rule: dict | None) -> str:
    if not rule:
        return ""
    value = rule["value"]
    if rule.get("on") == "change" and rule["op"] in ("<=", "<") and value <= 0:
        return f"a drop of {abs(value):g}{' or more' if rule['op'] == '<=' else ''}"
    if rule.get("on") == "change" and rule["op"] in (">=", ">") and value >= 0:
        return f"a rise of {value:g}{' or more' if rule['op'] == '>=' else ''}"
    return f"{'change' if rule.get('on') == 'change' else 'after value'} {rule['op']} {value:g}"


def derivation_text(calc: str | None, field: str, before: str | None, after: str | None, rule: dict | None) -> str:
    """The matrix's Analysis Derivation, in words."""
    if calc == "change_from_baseline":
        return f"{after} value minus {before} value, paired by subject"
    if calc == "responder_rate":
        return f"Responder: {rule_text(rule)} from {before} to {after}, out of subjects with both values"
    if calc == "descriptive":
        return f"{field} at {before or after}: per-subject mean of the readings, then n, mean, SD, median, min, max"
    if calc == "frequency":
        return f"{field} at {before or after}: count and percent per answer, out of subjects with an answer"
    if calc == "teae_count":
        start = f"the {before} visit date" if before else "each subject's first visit date"
        return f"Adverse events with {field} on or after {start}"
    return ""


def _placed(draft: DraftECRF) -> list[tuple[str, str, FieldDef]]:
    return [(form.visit, form.form, f) for form in draft.forms for f in form.fields]


def _forms_for(draft: DraftECRF, field: FieldDef | None, kind: str, before: str | None, after: str | None) -> str | None:
    """The forms holding this field at the row's visits, or at every visit for a
    safety row, which has none of its own."""
    if field is None:
        return None
    forms = [form for visit, form, f in _placed(draft) if f.name == field.name
             and (kind == "safety" or visit in (before, after))]
    return "; ".join(dict.fromkeys(forms)) or None


def _field(draft: DraftECRF, field_id: str) -> FieldDef | None:
    return next((f for _, _, f in _placed(draft) if f.field_id == field_id), None)


def _row(i: SapItem, draft: DraftECRF) -> dict:
    field = _field(draft, i.field_id)
    ftype = field.type if field else None
    calc = calculation_of(i.kind, i.responder_rule, ftype)
    return {"id": i.id, "label": i.label, "endpoint_concept": i.endpoint_concept, "kind": i.kind,
            "calculation": calc, "field_id": i.field_id, "field": field.name if field else None,
            "form": i.form or _forms_for(draft, field, i.kind, i.baseline_visit_id, i.analysis_visit_id),
            "baseline_visit_id": i.baseline_visit_id, "analysis_visit_id": i.analysis_visit_id, "unit": i.unit,
            "responder_rule": i.responder_rule, "method": i.method,
            "analysis_derivation": i.derivation or (derivation_text(calc, field.name, i.baseline_visit_id, i.analysis_visit_id,
                                                                    i.responder_rule) if field else None),
            "derivation": derivation(i.kind, i.responder_rule, ftype)}


def _form(s: Session, protocol_id: int) -> tuple[DraftECRF, int]:
    v = db.latest_version(s, protocol_id)
    if v is None:
        raise HTTPException(409, "Extract the form first; results point at its fields")
    return DraftECRF.model_validate(v.content), v.version


class SapIn(BaseModel):
    """The form sends field_id, the two visits, calculation and, for a responder
    rate, responder_rule. Everything else is optional and filled in when left
    out. kind is still accepted in place of calculation."""
    field_id: str
    calculation: str | None = None
    kind: str | None = None
    baseline_visit_id: str | None = None
    analysis_visit_id: str | None = None
    responder_rule: dict | None = None
    label: str | None = None
    endpoint_concept: str | None = None
    unit: str | None = None
    method: str | None = None


def _check(body: SapIn, kind: str, field: FieldDef, draft: DraftECRF) -> None:
    has = {visit for visit, _, f in _placed(draft) if f.name == field.name}
    for visit in (body.baseline_visit_id, body.analysis_visit_id):
        if visit and kind != "safety" and visit not in has:
            raise HTTPException(422, f"{field.name} is not collected at {visit}")
    if kind == "endpoint":
        if field.type not in NUMERIC:
            raise HTTPException(422, "Change from baseline needs a numeric field")
        if not body.baseline_visit_id or not body.analysis_visit_id:
            raise HTTPException(422, "Pick a before visit and an after visit")
        if body.baseline_visit_id == body.analysis_visit_id:
            raise HTTPException(422, "The before and after visits must differ")
    if kind == "safety" and field.type != "date":
        raise HTTPException(422, "Treatment-emergent adverse events need the adverse event's start date field")
    if kind in ("baseline", "disposition") and field.type == "date":
        raise HTTPException(422, "Pick a numeric or categorical field; a date has no summary here")
    if kind == "baseline" and not body.baseline_visit_id:
        raise HTTPException(422, "A baseline item needs a baseline visit")
    if kind == "disposition" and not body.analysis_visit_id:
        raise HTTPException(422, "A disposition item needs an analysis visit")
    rule = body.responder_rule
    if rule is not None:
        if kind != "endpoint":
            raise HTTPException(422, "Only a responder rate has a rule")
        if (rule.get("on") not in ("change", "analysis") or rule.get("op") not in RULE_OPS
                or not isinstance(rule.get("value"), int | float) or isinstance(rule.get("value"), bool)):
            raise HTTPException(422, "A responder rule is: on change or analysis, an operator, and a number")


def _values(s: Session, body: SapIn, draft: DraftECRF, protocol_id: int, current: SapItem | None) -> dict:
    """Check the body and work out every column it does not give."""
    field = _field(draft, body.field_id)
    if field is None:
        raise HTTPException(422, "That field is not on this form")
    if body.calculation is not None:
        choice = CHOICES.get(body.calculation)
        if choice is None:
            raise HTTPException(422, f"Calculation must be one of: {', '.join(CHOICES)}")
        if field.type not in choice["types"]:
            raise HTTPException(422, f"{choice['label']} does not fit a {field.type} field")
        kind = _kind_for(body.calculation, body.baseline_visit_id, body.analysis_visit_id)
        if body.calculation == "responder_rate" and not body.responder_rule:
            raise HTTPException(422, "A responder rate needs its rule, for example a drop of 10 or more")
        if body.calculation == "change_from_baseline" and body.responder_rule:
            raise HTTPException(422, "Pick responder rate to use a rule")
    elif body.kind in KINDS:
        kind = body.kind
    else:
        raise HTTPException(422, f"Pick a calculation: {', '.join(CHOICES)}")
    _check(body, kind, field, draft)

    calc = calculation_of(kind, body.responder_rule, field.type)
    label = (body.label or "").strip()
    if not label:
        label = current.label if current else _next_label(s, protocol_id, kind)
    default_concept = f"{field.name} {CHOICES[calc]['label'].lower()}" if calc else field.name
    concept = (body.endpoint_concept or "").strip() or default_concept
    return {"label": label, "endpoint_concept": concept, "kind": kind, "field_id": body.field_id,
            "baseline_visit_id": body.baseline_visit_id, "analysis_visit_id": body.analysis_visit_id,
            "unit": body.unit or field.unit, "responder_rule": body.responder_rule,
            "method": body.method or (CHOICES[calc]["method"] if calc else None),
            "form": _forms_for(draft, field, kind, body.baseline_visit_id, body.analysis_visit_id),
            "derivation": derivation_text(calc, field.name, body.baseline_visit_id, body.analysis_visit_id, body.responder_rule)}


def _next_label(s: Session, protocol_id: int, kind: str) -> str:
    n = len(s.scalars(select(SapItem.id).where(SapItem.protocol_id == protocol_id, SapItem.kind == kind)).all())
    return f"{_KIND_LABEL[kind]} {n + 1}"


def _log(s: Session, cu: CurrentUser, p: Protocol, version: int, item: SapItem, old: dict | None, new: dict | None) -> None:
    def text(v):
        return json.dumps(v)[:1000] if v is not None else None
    s.add(FormFieldHistory(protocol_id=p.id, version=version, field_id=item.field_id, attribute=f"sap_item:{item.id}",
                           old_value=text(old), new_value=text(new), by=cu.user.email))


def _item(s: Session, protocol_id: int, item_id: int) -> SapItem:
    i = s.get(SapItem, item_id)
    if i is None or i.protocol_id != protocol_id:
        raise HTTPException(404, "result not found")
    return i


@router.get("/{protocol_id}/sap")
def list_items(protocol_id: int, cu: CurrentUser = Depends(require("dashboard.view")),
               s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    draft, _ = _form(s, protocol_id)
    rows = s.scalars(select(SapItem).where(SapItem.protocol_id == protocol_id).order_by(SapItem.id))
    return {"items": [_row(i, draft) for i in rows], "kinds": list(KINDS), "operators": list(RULE_OPS),
            "calculations": [{"name": k, "label": v["label"], "types": list(v["types"]),
                              "formula": CALCULATIONS[k]["formula"]} for k, v in CHOICES.items()],
            "visits": list(dict.fromkeys(f.visit for f in draft.forms)),
            "fields": [{"field_id": f.field_id, "name": f.name, "visit": visit, "form": form, "type": f.type, "unit": f.unit}
                       for visit, form, f in _placed(draft)]}


@router.post("/{protocol_id}/sap")
def add_item(protocol_id: int, body: SapIn, cu: CurrentUser = Depends(require("sap.edit")),
             s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    scope.check_study_open(p)
    draft, version = _form(s, protocol_id)
    i = SapItem(protocol_id=protocol_id, **_values(s, body, draft, protocol_id, None))
    s.add(i)
    s.flush()
    _log(s, cu, p, version, i, None, _row(i, draft))
    s.commit()
    return _row(i, draft)


@router.put("/{protocol_id}/sap/{item_id}")
def edit_item(protocol_id: int, item_id: int, body: SapIn, cu: CurrentUser = Depends(require("sap.edit")),
              s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    scope.check_study_open(p)
    i = _item(s, protocol_id, item_id)
    draft, version = _form(s, protocol_id)
    before = _row(i, draft)
    for key, value in _values(s, body, draft, protocol_id, i).items():
        setattr(i, key, value)
    _log(s, cu, p, version, i, before, _row(i, draft))
    s.commit()
    return _row(i, draft)


@router.delete("/{protocol_id}/sap/{item_id}")
def delete_item(protocol_id: int, item_id: int, cu: CurrentUser = Depends(require("sap.edit")),
                s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    scope.check_study_open(p)
    i = _item(s, protocol_id, item_id)
    draft, version = _form(s, protocol_id)
    _log(s, cu, p, version, i, _row(i, draft), None)
    s.delete(i)
    s.commit()
    return {"deleted": item_id}


# ------------------------------------------------------- traceability matrix

def matrix(s: Session, protocol_id: int) -> dict:
    """One row per result, in MATRIX_COLUMNS order. The caller checks scope."""
    v = db.locked_version(s, protocol_id) or db.latest_version(s, protocol_id)
    if v is None:
        raise HTTPException(409, "Extract the form first; results point at its fields")
    draft = DraftECRF.model_validate(v.content)
    rows = []
    for i in s.scalars(select(SapItem).where(SapItem.protocol_id == protocol_id).order_by(SapItem.id)):
        r = _row(i, draft)
        visits = " → ".join(x for x in (i.baseline_visit_id, i.analysis_visit_id) if x) or "All visits with this field"
        rows.append([r["label"], r["endpoint_concept"], r["form"] or "", r["field"] or "not on the form", visits,
                     r["unit"] or "", r["analysis_derivation"] or "", r["method"] or ""])
    return {"columns": MATRIX_COLUMNS, "rows": rows, "version": v.version, "locked": v.state == "locked"}


@router.get("/{protocol_id}/traceability")
def traceability(protocol_id: int, cu: CurrentUser = Depends(require("dashboard.view")),
                 s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    return {"protocol": p.name, **matrix(s, protocol_id)}
