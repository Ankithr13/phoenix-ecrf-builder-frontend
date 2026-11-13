"""The built-in checks, generated when a form is locked.

They bind by CDASH code first and by name second, so they work on any protocol:
a check whose fields are not on the form simply is not generated. EC-011 is not
here: it needs an intervention form this system does not model.

Soft by default. Only `format` checks are hard, and a format check here is what
the field's own type already demands.
"""

import re
from dataclasses import dataclass

from ecrf.foundation import VISIT as FOUNDATION
from ecrf.schema import DraftECRF, FieldDef, VisitForm

VISIT_DATE_CODE = "SVSTDTC"

# The Owner column of the client's Edit Check Specification, section 4. REQ and
# FMT are not in that table; they go to data management.
OWNERS = {"EC-001": "DM", "EC-002": "DM", "EC-003": "DM/Monitor", "EC-004": "DM/Clinical", "EC-005": "Site",
          "EC-006": "DM", "EC-007": "DM", "EC-008": "DM", "EC-009": "Safety/DM", "EC-010": "DM", "EC-012": "DM"}
DEFAULT_OWNER = "DM"


@dataclass
class CheckSpec:
    code: str
    type: str
    message: str
    field_ids: list[str]
    logic: dict
    form: str | None = None
    severity: str = "soft"


def _live(form: VisitForm) -> list[FieldDef]:
    return [f for f in form.fields if f.status != "rejected" and f.collected]


def _find(form: VisitForm, codes: tuple[str, ...], name: str | None = None) -> FieldDef | None:
    fields = _live(form)
    for f in fields:
        if f.cdash in codes:
            return f
    if name:
        for f in fields:
            if re.search(name, f.name, re.IGNORECASE):
                return f
    return None


def _per_form(draft: DraftECRF, fn) -> list[CheckSpec]:
    out = []
    for form in draft.forms:
        made = fn(form)
        if made:
            out.append(made)
    return out


def _dbp_below_sbp(form: VisitForm) -> CheckSpec | None:
    dbp = _find(form, ("DIABP",), r"\bdiastolic\b")
    sbp = _find(form, ("SYSBP",), r"\bsystolic\b")
    if not (dbp and sbp):
        return None
    return CheckSpec("EC-007", "cross_field", "Diastolic blood pressure is not below systolic. Please check both values.",
                     [dbp.field_id, sbp.field_id], {"a": dbp.field_id, "b": sbp.field_id, "op": "<"}, form.visit)


def _ae_dates(form: VisitForm) -> CheckSpec | None:
    start = _find(form, ("AESTDTC",), r"\b(ae|adverse event)\b.*\bstart\b")
    end = _find(form, ("AEENDTC",), r"\b(ae|adverse event)\b.*\b(end|stop)\b")
    if not (start and end):
        return None
    return CheckSpec("EC-008", "temporal", "The adverse event end date is before its start date. Please check both dates.",
                     [end.field_id, start.field_id], {"a": end.field_id, "b": start.field_id, "op": "on_or_after"}, form.visit)


_SERIOUS_CRITERIA = ("AESDTH", "AESLIFE", "AESHOSP", "AESDISAB", "AESCONG", "AESMIE")


def _serious_criteria(form: VisitForm) -> CheckSpec | None:
    serious = _find(form, ("AESER",), r"\bserious\b")
    criteria = [f for f in _live(form) if f.cdash in _SERIOUS_CRITERIA]
    if not (serious and criteria):
        return None
    ids = [f.field_id for f in criteria]
    return CheckSpec("EC-009", "conditional", "This adverse event is marked serious but no seriousness criterion is recorded.",
                     [serious.field_id, *ids], {"if_field": serious.field_id, "equals": "Yes", "then_any": ids}, form.visit)


def _conmed_dates(form: VisitForm) -> CheckSpec | None:
    start = _find(form, ("CMSTDTC",), r"\b(con.?med|concomitant).*\bstart\b")
    stop = _find(form, ("CMENDTC",), r"\b(con.?med|concomitant).*\b(stop|end)\b")
    if not (start and stop):
        return None
    return CheckSpec("EC-010", "temporal", "The medication stop date is before its start date. Please check both dates.",
                     [stop.field_id, start.field_id], {"a": stop.field_id, "b": start.field_id, "op": "on_or_after"}, form.visit)


def _completion(form: VisitForm) -> CheckSpec | None:
    if form.visit == FOUNDATION:
        return None
    status = _find(form, ("DSDECOD",), r"\bcompletion status\b")
    when = _find(form, ("DSSTDTC",), r"\bcompletion date\b")
    why = _find(form, ("DSTERM",), r"\b(completion|discontinuation|withdrawal) reason\b|\breason for (discontinuation|withdrawal)\b")
    if not (status and when and why):
        return None
    return CheckSpec("EC-012", "conditional", "A completion status is recorded without its date or reason.",
                     [status.field_id, when.field_id, why.field_id],
                     {"if_field": status.field_id, "then_required": [when.field_id, why.field_id]}, form.visit)


def specs(draft: DraftECRF) -> list[CheckSpec]:
    out: list[CheckSpec] = []
    base = next((f for f in draft.forms if f.visit == FOUNDATION), None)
    visits = [f for f in draft.forms if f.visit != FOUNDATION]
    visit_dates = {f.visit: _find(f, (VISIT_DATE_CODE,)) for f in visits}
    first_date = next((visit_dates[f.visit] for f in visits if visit_dates[f.visit]), None)

    covered: set[str] = set()
    if base:
        yob = _find(base, ("BRTHDTC",))
        consent = _find(base, ("RFICDTC",))
        eligible = _find(base, ("IEYN",))
        if yob:
            out.append(CheckSpec("EC-001", "required", "Year of birth is missing.", [yob.field_id], {}, base.visit))
            covered.add(yob.field_id)
        if yob and consent:
            out.append(CheckSpec("EC-002", "temporal", "Year of birth is not before the year of consent. Please check both.",
                                 [yob.field_id, consent.field_id],
                                 {"a": yob.field_id, "b": consent.field_id, "op": "before", "granularity": "year"}, base.visit))
        if consent and first_date:
            out.append(CheckSpec("EC-003", "temporal", "The consent date is after the first visit date. Please check both dates.",
                                 [consent.field_id, first_date.field_id],
                                 {"a": consent.field_id, "b": first_date.field_id, "op": "on_or_before"}))
        if eligible:
            out.append(CheckSpec("EC-004", "conditional", "This patient is marked not eligible, but a later visit has data.",
                                 [eligible.field_id], {"if_field": eligible.field_id, "equals": "No", "then_no_later_data": True}))

    for form in visits:
        d = visit_dates[form.visit]
        if d:
            out.append(CheckSpec("EC-005", "required", "Enter visit date or document visit not performed.", [d.field_id], {}, form.visit))
            covered.add(d.field_id)

    for form in draft.forms:
        for f in _live(form):
            if f.type in ("integer", "decimal") and (f.min is not None or f.max is not None):
                lo = "…" if f.min is None else f"{f.min:g}"
                hi = "…" if f.max is None else f"{f.max:g}"
                out.append(CheckSpec("EC-006", "range", f"{f.name} is outside the expected range {lo} to {hi}. Please check the value.",
                                     [f.field_id], {"min": f.min, "max": f.max}, form.visit))

    out += _per_form(draft, _dbp_below_sbp)
    out += _per_form(draft, _ae_dates)
    out += _per_form(draft, _serious_criteria)
    out += _per_form(draft, _conmed_dates)
    out += _per_form(draft, _completion)

    for form in draft.forms:
        for f in _live(form):
            if f.required and f.field_id not in covered:
                out.append(CheckSpec("REQ", "required", f"{f.name} is missing.", [f.field_id], {}, form.visit))
            if f.type in ("date", "integer", "decimal"):
                out.append(CheckSpec("FMT", "format", f"{f.name} must be a valid {f.type}.", [f.field_id],
                                     {"kind": f.type}, form.visit, severity="hard"))
    return out
