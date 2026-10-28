"""Educated-guess ranges for numeric fields nobody else could fill.

Runs after the CDASH library, only on numeric fields still missing a
limit. The guess comes from the unit first (anything in mmHg sits between
0 and 300) and from the field name second (anything called "age" sits
between 0 and 120). These are plausibility limits that catch a misplaced
decimal, not clinical normal ranges, and they are deterministic code, so
the model is never asked to invent a number. The field keeps its flag and
the note says plainly that the range was guessed."""

import re

from ecrf.schema import FieldDef

# unit pattern -> (min, max). Order matters: first match wins.
BY_UNIT: list[tuple[str, tuple[float, float]]] = [
    (r"^mm\s?hg$", (0, 300)),
    (r"^(beats?/min|bpm|beats per minute)$", (20, 250)),
    (r"^(breaths?/min|breaths per minute|/min)$", (4, 80)),
    (r"^(°?c|celsius|deg ?c)$", (30, 45)),
    (r"^(°?f|fahrenheit|deg ?f)$", (86, 113)),
    (r"^kg$", (2, 300)),
    (r"^(lb|lbs|pounds)$", (4, 660)),
    (r"^cm$", (20, 250)),
    (r"^m$", (0.3, 2.5)),
    (r"^(in|inch|inches)$", (8, 100)),
    (r"^kg/m\^?2$", (10, 80)),
    (r"^%$", (0, 100)),
    (r"^(ms|msec|milliseconds?)$", (0, 3000)),
    (r"^(s|sec|seconds?)$", (0, 3600)),
    (r"^(min|minutes?)$", (0, 1440)),
    (r"^(h|hr|hours?)$", (0, 720)),
    (r"^(d|days?)$", (0, 3650)),
    (r"^(wk|weeks?)$", (0, 520)),
    (r"^(mo|months?)$", (0, 120)),
    (r"^(y|yr|yrs|years?)$", (0, 120)),
    (r"^mg/dl$", (0, 2000)),
    (r"^mmol/l$", (0, 100)),
    (r"^g/dl$", (0, 30)),
    (r"^g/l$", (0, 300)),
    (r"^(u/l|iu/l)$", (0, 10000)),
    (r"^(meq/l)$", (0, 300)),
    (r"^ml/min(/1\.73\s?m\^?2)?$", (0, 300)),
    (r"^(ml|cc)$", (0, 5000)),
    (r"^(l|liters?|litres?)$", (0, 50)),
    (r"^mg$", (0, 10000)),
    (r"^(mcg|ug|µg)$", (0, 100000)),
    (r"^(ng/ml|pg/ml)$", (0, 100000)),
    (r"^(10\^3/ul|10\^9/l|x10\^3/ul|k/ul)$", (0, 2000)),
    (r"^(10\^6/ul|10\^12/l)$", (0, 20)),
    (r"^(mmol/mol)$", (0, 200)),
]

# name pattern -> (min, max), for numeric fields with no usable unit.
BY_NAME: list[tuple[str, tuple[float, float]]] = [
    (r"\bage\b", (0, 120)),
    (r"\b(spo2|oxygen saturation|o2 sat)", (50, 100)),
    (r"\b(pain|nrs|vas)\b.*(score|scale)|\b(score|scale)\b.*\bpain\b", (0, 10)),
    (r"\bbmi\b|body mass index", (10, 80)),
    (r"\b(systolic|diastolic)\b", (0, 300)),
    (r"\b(heart rate|pulse)\b", (20, 250)),
    (r"\b(respiratory rate|respirations?)\b", (4, 80)),
    (r"\btemperature\b", (30, 45)),
    (r"\bweight\b", (2, 300)),
    (r"\bheight\b", (20, 250)),
    (r"\b(number of|count|episodes?|events?)\b", (0, 1000)),
    (r"\b(duration|days? since|time since)\b", (0, 3650)),
    (r"\b(dose|dosage)\b", (0, 10000)),
    (r"\b(percent|percentage)\b", (0, 100)),
]


def _lookup(table, text: str | None) -> tuple[float, float] | None:
    if not text:
        return None
    t = text.strip().lower()
    for pat, rng in table:
        if re.search(pat, t):
            return rng
    return None


def fill(field: FieldDef) -> FieldDef:
    """Guess min/max for a numeric field that still has neither. Marks the
    field so the reviewer sees it was a guess."""
    if field.type not in ("integer", "decimal"):
        return field
    if field.min is not None or field.max is not None:
        return field
    rng = _lookup(BY_UNIT, field.unit) or _lookup(BY_NAME, field.name)
    if rng is None:
        return field
    field.min, field.max = rng
    field.suggested = [*field.suggested, "min", "max"]
    field.suggested_from = "heuristic" if field.suggested_from is None else field.suggested_from
    basis = f"the unit {field.unit}" if _lookup(BY_UNIT, field.unit) else "the field name"
    lo = int(rng[0]) if float(rng[0]).is_integer() else rng[0]
    hi = int(rng[1]) if float(rng[1]).is_integer() else rng[1]
    field.issue_note = ((field.issue_note or "").rstrip() +
                        f" Range {lo} to {hi} is an educated guess from {basis}, not from the "
                        "protocol or the CDASH library. Check it before approving.").strip()
    return field
