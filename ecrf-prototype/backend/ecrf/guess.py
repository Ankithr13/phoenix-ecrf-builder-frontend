"""Educated-guess units and ranges for numeric fields nobody else could fill.

Runs last, after the protocol text search and the CDASH library, only on
numeric fields still missing a unit or a limit. The unit comes from the
field name (anything called "creatinine" is in mg/dL), then the range
comes from the unit first (anything in mmHg sits between 0 and 300) and
from the field name second (anything called "age" sits between 0 and 120).
These are plausibility limits that catch a misplaced decimal, not clinical
normal ranges, and they are deterministic code, so the model is never
asked to invent a number. The field keeps its flag and the note says
plainly what was guessed and from what, so the reviewer can accept it in
one click or correct it."""

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
    (r"^(m|meters?|metres?)$", (0, 1000)),
    (r"^(in|inch|inches)$", (8, 100)),
    (r"^kg/m\^?2$", (10, 80)),
    (r"^%$", (0, 100)),
    (r"^%\s*(predicted|pred\.?|of predicted)$", (0, 300)),
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
    (r"^ml/min/mmhg$", (0, 100)),
    (r"^l/min$", (0, 60)),
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
    (r"\bborg\b", (0, 10)),
    (r"\b(nyha|who)\b.*\b(class|functional)", (1, 4)),
    (r"\bbmi\b|body mass index", (10, 80)),
    (r"\b(systolic|diastolic)\b", (0, 300)),
    (r"\b(heart rate|pulse)\b", (20, 250)),
    (r"\b(respiratory rate|respirations?)\b", (4, 80)),
    (r"\btemperature\b", (30, 45)),
    (r"\bweight\b", (2, 300)),
    (r"\bheight\b", (20, 250)),
    (r"\b(number of|count|episodes?|events?|hospitali[sz]ations?|exacerbations?)\b", (0, 1000)),
    (r"\b(duration|days? since|time since)\b", (0, 3650)),
    (r"\b(dose|dosage)\b", (0, 10000)),
    (r"\b(percent|percentage|% predicted)\b", (0, 100)),
    (r"\b(score|scale|grade|stage|class)\b", (0, 100)),
]

# name pattern -> unit, for numeric fields with no unit at all. The range
# then follows from the unit.
UNIT_BY_NAME: list[tuple[str, str]] = [
    (r"\b(systolic|diastolic|blood pressure|\bbp\b|arterial pressure|pulmonary.*pressure|wedge pressure)", "mmHg"),
    (r"\b(heart rate|pulse|\bhr\b)\b", "beats/min"),
    (r"\b(respiratory rate|respirations?|\brr\b)\b", "breaths/min"),
    (r"\btemperature\b", "C"),
    (r"\bweight\b", "kg"),
    (r"\bheight\b", "cm"),
    (r"\bbmi\b|body mass index", "kg/m2"),
    (r"\b(spo2|oxygen saturation|o2 sat|hematocrit|haematocrit|hba1c|% predicted|percent|percentage)\b", "%"),
    (r"\b(qt|qtc|qtcf|qtcb|pr interval|qrs|rr interval|ecg.*interval)\b", "ms"),
    (r"\b(walk distance|6mwd|6-minute walk|six.minute walk|distance)\b", "m"),
    (r"\b(fev1|fvc|tlc|forced vital capacity|forced expiratory|lung capacity|vital capacity)\b", "L"),
    (r"\b(dlco|diffusing capacity)\b", "mL/min/mmHg"),
    (r"\b(nt-?probnp|bnp|natriuretic)\b", "pg/mL"),
    (r"\b(oxygen flow|supplemental oxygen|o2 flow|flow rate)\b", "L/min"),
    (r"\b(sodium|potassium|chloride|bicarbonate|hco3|\bna\b|\bk\b)\b", "mEq/L"),
    (r"\b(creatinine|glucose|urea nitrogen|\bbun\b|calcium|bilirubin|cholesterol|\bldl\b|\bhdl\b|triglycerides?|uric acid|phosph(orus|ate))\b", "mg/dL"),
    (r"\b(albumin|hemoglobin|haemoglobin|total protein)\b", "g/dL"),
    (r"\b(alt|ast|alkaline phosphatase|\balp\b|aminotransferase|transaminase|ggt|gamma.glutamyl|lipase|amylase|creatine kinase|\bck\b|\bldh\b)\b", "U/L"),
    (r"\b(egfr|glomerular filtration|creatinine clearance)\b", "mL/min/1.73m2"),
    (r"\b(white blood cell|wbc|leukocyte|platelet|neutrophil|lymphocyte|monocyte|eosinophil|basophil)\b", "10^3/uL"),
    (r"\b(red blood cell|rbc|erythrocyte)\b", "10^6/uL"),
    (r"\b(troponin|ferritin|tsh|vitamin|hormone|insulin|c-reactive|crp|interleukin|cytokine)\b", "ng/mL"),
    (r"\b(hcg|pregnancy)\b", "mIU/mL"),
    (r"\bage\b", "years"),
    (r"\b(duration|time since|days since|interval|time to)\b", "days"),
    (r"\b(dose|dosage)\b", "mg"),
    (r"\b(volume|urine output)\b", "mL"),
]


def _lookup(table, text: str | None):
    if not text:
        return None
    t = text.strip().lower()
    for pat, val in table:
        if re.search(pat, t):
            return val
    return None


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def fill(field: FieldDef) -> FieldDef:
    """Guess the unit and whichever of min/max a numeric field still lacks.
    Marks the field so the reviewer sees it was a guess."""
    if field.type not in ("integer", "decimal"):
        return field
    filled: list[str] = []
    basis: list[str] = []
    if field.unit is None:
        unit = _lookup(UNIT_BY_NAME, field.name)
        if unit:
            field.unit = unit
            filled.append("unit")
            basis.append("the field name")
    if field.min is None or field.max is None:
        rng = _lookup(BY_UNIT, field.unit)
        from_unit = rng is not None
        # A unit nobody recognises ("L and % predicted"): fall back to the
        # range for the unit the name implies, then to the name itself.
        rng = rng or _lookup(BY_UNIT, _lookup(UNIT_BY_NAME, field.name)) or _lookup(BY_NAME, field.name)
        if rng is not None:
            if field.min is None:
                field.min = rng[0]
                filled.append("min")
            if field.max is None:
                field.max = rng[1]
                filled.append("max")
            if "min" in filled or "max" in filled:
                basis.append(f"the unit {field.unit}" if from_unit and "unit" not in filled else "the field name")
    if not filled:
        return field
    field.suggested = [*field.suggested, *filled]
    field.suggested_from = "heuristic"
    parts = []
    if "min" in filled or "max" in filled:
        parts.append(f"range {_fmt(field.min)} to {_fmt(field.max)}")
    if "unit" in filled:
        parts.append(f"unit {field.unit}")
    seen_basis = " and ".join(dict.fromkeys(basis))
    what = ", ".join(parts)
    field.issue_note = ((field.issue_note or "").rstrip() +
                        f" {what[0].upper() + what[1:]} is an educated guess from {seen_basis}, "
                        "not from the protocol or the CDASH library. Check it before approving.").strip()
    return field
