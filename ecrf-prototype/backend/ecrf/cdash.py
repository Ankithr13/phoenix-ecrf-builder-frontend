"""CDASH enrichment. Deterministic, no model.

After extraction and verification, each surviving field is matched against
the library by name (aliases first, then fuzzy). A match attaches the CDASH
code and domain, and fills in type, unit or range the model left blank.

It never adds fields the model did not produce. Anything the library thinks
is missing is returned separately as a suggestion, clearly labelled as not
coming from the protocol, so the grounding guarantee stays honest.
"""

from functools import lru_cache

import yaml
from rapidfuzz import fuzz, process

from ecrf.config import config
from ecrf.schema import FieldDef, VisitForm


@lru_cache(maxsize=1)
def library() -> dict:
    with open(config.data_dir / "cdash_library.yaml") as f:
        return yaml.safe_load(f)["domains"]


@lru_cache(maxsize=1)
def _index() -> dict[str, tuple[str, dict]]:
    """lowercase name/alias -> (domain, field entry)"""
    idx: dict[str, tuple[str, dict]] = {}
    for dom, d in library().items():
        for fld in d["fields"]:
            idx[fld["name"].lower()] = (dom, fld)
            for a in fld.get("aliases", []):
                idx[a.lower()] = (dom, fld)
    return idx


def match(name: str, min_score: int = 85) -> tuple[str, dict] | None:
    idx = _index()
    key = name.strip().lower()
    if key in idx:
        return idx[key]
    best = process.extractOne(key, list(idx.keys()), scorer=fuzz.token_set_ratio)
    if best and best[1] >= min_score:
        return idx[best[0]]
    return None


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def enrich(field: FieldDef) -> FieldDef:
    """Attach the code and fill gaps from the library. Two kinds of range
    exist in the library: min/max transcribed from the client document, and
    suggest_min/suggest_max, wide plausibility limits added for fields the
    client document leaves open. Both are recorded in field.suggested so the
    reviewer can see what the protocol did not say."""
    hit = match(field.name)
    if not hit:
        return field
    dom, entry = hit
    field.cdash = entry.get("cdash")
    field.domain = dom
    filled: list[str] = []
    if field.unit is None and entry.get("unit"):
        field.unit = entry["unit"]
        filled.append("unit")
    lo = entry.get("min", entry.get("suggest_min"))
    hi = entry.get("max", entry.get("suggest_max"))
    if field.min is None and lo is not None:
        field.min = lo
        filled.append("min")
    if field.max is None and hi is not None:
        field.max = hi
        filled.append("max")
    if field.choices is None and entry.get("choices"):
        field.choices = entry["choices"]
        filled.append("choices")
    field.suggested = filled
    if filled:
        field.suggested_from = "library"
    if filled and field.issue == "missing":
        parts = []
        if "min" in filled or "max" in filled:
            parts.append(f"range {_fmt(field.min) if field.min is not None else '…'}"
                         f" to {_fmt(field.max) if field.max is not None else '…'}")
        if "unit" in filled:
            parts.append(f"unit {field.unit}")
        if "choices" in filled:
            parts.append("choices " + " / ".join(field.choices or []))
        field.issue_note = ((field.issue_note or "").rstrip() + " Suggested from the CDASH library "
                            f"({field.cdash}): {', '.join(parts)}. The protocol does not state this; "
                            "approve to accept the suggestion or edit it first.").strip()
    return field


def suggestions(form: VisitForm) -> list[dict]:
    """Standard fields the library has for the domains present in this form
    that the model did NOT produce. Not grounded in the protocol. Shown to
    the reviewer as 'the library also defines these', nothing more."""
    present = {f.cdash for f in form.fields if f.cdash}
    domains = {f.domain for f in form.fields if f.domain}
    out = []
    for dom in domains:
        for entry in library()[dom]["fields"]:
            if entry["cdash"] not in present:
                out.append({"domain": dom, "name": entry["name"],
                            "cdash": entry["cdash"], "type": entry.get("type"),
                            "unit": entry.get("unit")})
    return out
