"""A fixed registry of approved calculations.

There is no general query path. The dashboard is built from CALCULATIONS and
from the sponsor's SAP rows, which only choose what each calculation works on.
The absence of a free-text input IS the enforcement.
"""

from collections.abc import Callable

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.schema import DraftECRF
from ecrf.stats import calculations
from ecrf.stats.calculations import Analysis
from ecrf.storage.models import Observation, SapItem, Subject


class UnsupportedAnalysis(Exception):
    """Raised for anything not in the registry. Never approximate."""


KINDS = ("endpoint", "safety", "disposition", "baseline")
VISIT_DATE_CODE = "SVSTDTC"

CALCULATIONS: dict[str, dict] = {
    "descriptive": {
        "label": "Descriptive statistics",
        "fn": calculations.descriptive,
        "kinds": ("endpoint", "baseline", "disposition"),
    },
    "change_from_baseline": {
        "label": "Change from baseline",
        "fn": calculations.change_from_baseline,
        "kinds": ("endpoint",),
    },
    "responder_rate": {
        "label": "Responder rate",
        "fn": calculations.responder_rate,
        "kinds": ("endpoint",),
        "needs_rule": True,
    },
    "teae_count": {
        "label": "Treatment-emergent adverse events",
        "fn": calculations.teae_count,
        "kinds": ("safety",),
    },
    "percent_missing": {
        "label": "Missing values",
        "fn": calculations.percent_missing,
        "kinds": KINDS,
    },
}


def available() -> list[dict]:
    return [{"name": k, "label": v["label"], "kinds": list(v["kinds"])} for k, v in CALCULATIONS.items()]


def applicable(kind: str, rule: dict | None) -> list[str]:
    """Which calculations a row of this kind gets."""
    return [name for name, c in CALCULATIONS.items()
            if kind in c["kinds"] and (rule or not c.get("needs_rule"))]


COLUMNS = ["subject_id", "visit", "field_name", "repeat_num", "value_num", "value_text"]


def load_frame(s: Session, protocol_id: int, site_ids: frozenset[int] | list[int] | None = None) -> pd.DataFrame:
    """Approved rows only, within the caller's sites. A value the sponsor has
    not approved is not data yet, and the independent script applies the same
    rule in its own SQL."""
    q = select(Observation).where(Observation.protocol_id == protocol_id, Observation.status == "approved")
    if site_ids is not None:
        q = q.join(Subject, Subject.id == Observation.subject_ref).where(Subject.site_org_id.in_(site_ids))
    rows = s.scalars(q).all()
    return pd.DataFrame([{c: getattr(r, c) for c in COLUMNS} for r in rows], columns=COLUMNS)


def resolve(item: SapItem, draft: DraftECRF, subjects: int) -> Analysis | None:
    """Turn a SAP row into what the calculations need. None when its field is
    no longer on the form, so the result reads as not available."""
    fields = [(form.visit, f) for form in draft.forms for f in form.fields]
    name = next((f.name for _, f in fields if f.field_id == item.field_id), None)
    if name is None:
        return None
    slots = {visit: f.repeats for visit, f in fields if f.name == name and f.collected}
    if item.kind != "safety":
        slots = {v: n for v, n in slots.items() if v in (item.baseline_visit_id, item.analysis_visit_id)}
    visit_date = next((f.name for _, f in fields if f.cdash == VISIT_DATE_CODE), None)
    return Analysis(kind=item.kind, field=name, baseline=item.baseline_visit_id, analysis=item.analysis_visit_id,
                    rule=item.responder_rule, expected=slots, subjects=subjects, visit_date=visit_date)


def run(name: str, df: pd.DataFrame, a: Analysis):
    c = CALCULATIONS.get(name)
    if c is None or a.kind not in c["kinds"] or (c.get("needs_rule") and not a.rule):
        raise UnsupportedAnalysis(name)
    fn: Callable = c["fn"]
    return fn(df, a)
