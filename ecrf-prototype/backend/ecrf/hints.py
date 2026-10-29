"""Units and ranges the protocol does state, found by code.

Runs on each surviving field before the CDASH library and the heuristic
guess. The model is told to give a unit or range only when the protocol
states one, and it regularly misses one stated somewhere other than the
assessment section: the eligibility criteria carry the blood pressure
limits, a lab appendix carries the unit, the statistics section carries
the minimum walk distance. This step searches the normalised protocol
text for the field's name and its library aliases and reads a range or a
unit out of the sentence that follows each hit.

It is regular expressions over the same text the grounding check uses, so
it cannot be talked into inventing a value, and every value it fills is
recorded with the sentence it came from. Because the value IS in the
protocol, a field whose every gap this step closed is no longer missing
anything and its flag is cleared. A field it could only partly fill keeps
the flag and goes on to the library and the guess.

Precision over recall, three ways:
  * a number counts only when a recognised unit follows it, so "Week 4 to
    Week 8" and "sections 3 to 5" never become validation limits;
  * the unit must agree with the unit the model or the library already
    gave the field, or with one the protocol prints in brackets right
    after the name, so "at least 5 minutes of rest" in the vital signs
    paragraph cannot become the heart rate's minimum and "drawn 10 to 60
    minutes after dosing" cannot become an NT-proBNP range. When nobody
    knows the unit, no number is read at all. A unit learned only from
    the brackets is filled in but the flag is kept;
  * only the first statement after each hit is read, so a sentence that
    goes on to give the diastolic limits does not widen the systolic ones.
When several hits state different limits, the widest wins: the eligibility
window (140 to 159 mmHg) is a subset of the plausibility window (60 to 250
mmHg), and a validation range must admit every value the study can
legitimately record.
"""

import re

from ecrf import cdash
from ecrf.ingest import Document
from ecrf.schema import FieldDef

# Units the text search recognises, longest alternatives first so
# "mL/min/1.73 m2" is not read as "mL". Matched case-insensitively and
# followed by a non-letter.
_UNITS = [
    r"mL/min/1\.73\s?m\^?2", r"mL/min/mmHg", r"mL/min", r"mm\s?Hg", r"mmol/mol", r"mmol/L",
    r"mg/dL", r"g/dL", r"g/L", r"mEq/L", r"IU/L", r"U/L", r"mIU/mL", r"pg/mL", r"ng/mL",
    r"ng/L", r"µg/L", r"ug/L", r"mcg/L", r"10\^3/[uµ]L", r"10\^9/L", r"10\^6/[uµ]L", r"10\^12/L",
    r"kg/m\^?2", r"beats\s?(?:per|/)\s?min(?:ute)?", r"breaths\s?(?:per|/)\s?min(?:ute)?",
    r"bpm", r"msec", r"ms", r"seconds?", r"minutes?", r"hours?", r"days?", r"weeks?",
    r"months?", r"years?", r"kg", r"lbs?", r"cm", r"mm", r"metres?", r"meters?", r"m",
    r"mL", r"L/min", r"L", r"°\s?[CF]", r"degrees\s?(?:celsius|fahrenheit|[CF])", r"%",
]
_UNIT = "(?:" + "|".join(_UNITS) + ")"
_NUM = r"(\d+(?:[.,]\d+)?)"
_END = r"(?![A-Za-z])"

# "between 60 and 250 mmHg", "60 to 250 mmHg", "60-250 mmHg", with an en or
# em dash as well as a hyphen
_RANGE = re.compile(
    rf"(?:between\s+)?{_NUM}\s*(?:to|and|-|\u2013|\u2014)\s*{_NUM}\s*({_UNIT}){_END}", re.IGNORECASE)
# ">= 150 meters", "at least 150 meters", "150 meters or more". Only the
# phrasings that state a bound are read. "more than 180 mmHg" and "less
# than 90 mmHg" are left alone: in a contraindication they are the limits
# of the danger zone, not of the field, and one 75-page protocol turned
# them into a systolic range of 180 to 90.
_MIN = re.compile(
    rf"(?:(?:≥|>=|at least|no less than|not less than|minimum(?: of)?)\s*"
    rf"{_NUM}\s*({_UNIT}){_END}|{_NUM}\s*({_UNIT})\s+or\s+(?:more|greater|higher|above)(?!\s+than){_END})",
    re.IGNORECASE)
_MAX = re.compile(
    rf"(?:(?:≤|<=|at most|no more than|not more than|maximum(?: of)?|up to)\s*"
    rf"{_NUM}\s*({_UNIT}){_END}|{_NUM}\s*({_UNIT})\s+or\s+(?:less|lower|below)(?!\s+than){_END})",
    re.IGNORECASE)
# "Weight (kg)", "temperature in °C"
_UNIT_NEAR = re.compile(rf"(?:\(\s*({_UNIT})\s*\)|\bin\s+({_UNIT}){_END})", re.IGNORECASE)

# A hit's sentence: this many characters after the name, cut at the first
# full stop that ends a sentence, and this many before it, cut at the last.
# The text after the name is read first; the text before it only when the
# text after said nothing ("must walk at least 150 meters on the 6-minute
# walk test"), because "systolic ... 60 to 250 mmHg and diastolic" would
# otherwise hand the systolic limits to the diastolic field.
_AFTER = 180
_BEFORE = 120
_SENTENCE_END = re.compile(r"\.\s+(?=[A-Z])")

# Qualifiers the model prefixes or suffixes to a name that the protocol
# itself rarely uses next to the value: "Practice 6-Minute Walk Distance",
# "Baseline FEV1 Absolute", "NT-proBNP Concentration".
_DROP_FIRST = re.compile(r"^(practice|peak|trough|baseline|screening|pre|post|resting|seated|"
                         r"supine|standing|mean|average|total|absolute|serum|plasma|blood|urine)\b[\s-]*",
                         re.IGNORECASE)
_DROP_LAST = re.compile(r"[\s-]*\b(absolute|value|result|results|level|levels|concentration|measurement|"
                        r"reading|distance|score|count|at rest|at screening|at baseline|pre-\S+|post-\S+)$",
                        re.IGNORECASE)

NUMERIC = ("integer", "decimal")
# A count has no unit, so a count with both limits is complete.
_COUNT = re.compile(r"\b(number of|count|episodes?|events?|hospitali[sz]ations?|exacerbations?)\b", re.IGNORECASE)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _norm_unit(u: str) -> str:
    u = re.sub(r"\s+", "", u)
    low = u.lower()
    if low == "mmhg":
        return "mmHg"
    if low in ("bpm", "beatspermin", "beats/min", "beatsperminute", "beats/minute"):
        return "beats/min"
    if low.startswith("breaths"):
        return "breaths/min"
    if low in ("meter", "meters", "metre", "metres"):
        return "m"
    if low == "msec":
        return "ms"
    if low in ("°c", "degreesc", "degreescelsius"):
        return "C"
    if low in ("°f", "degreesf", "degreesfahrenheit"):
        return "F"
    return u


def _same_unit(expected: str | None, found: str) -> bool:
    if not expected:
        return True
    return _norm_unit(expected).lower() == _norm_unit(found).lower()


def _library_entry(field: FieldDef) -> dict | None:
    hit = cdash.match(field.name)
    return hit[1] if hit else None


def _names_for(field: FieldDef, entry: dict | None) -> list[str]:
    """The field's own name, the library's canonical name and its aliases.
    Short all-caps aliases (HR, RR, K) match only as whole capitalised
    words, or "K" would hit every "kg"."""
    names = [field.name]
    if entry:
        names.append(entry["name"])
        names.extend(entry.get("aliases", []))
    # Also the field name with one qualifier stripped from either end, as
    # long as what is left is still a phrase, so "Walk" alone never matches.
    own = re.sub(r"\s*\(.*?\)\s*", " ", field.name).strip()
    for variant in (_DROP_FIRST.sub("", own), _DROP_LAST.sub("", own),
                    _DROP_LAST.sub("", _DROP_FIRST.sub("", own))):
        if variant != own and (" " in variant or len(variant) >= 5):
            names.append(variant)
    out, seen = [], set()
    for n in names:
        n = re.sub(r"\s*\(.*?\)\s*", " ", n).strip()
        if len(n) >= 2 and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def _windows(text: str, name: str) -> list[tuple[str, str]]:
    """(text before the hit, text from the hit on), both within the sentence."""
    if len(name) <= 3 and name.isupper():
        pat = re.compile(rf"\b{re.escape(name)}\b")
    else:
        pat = re.compile(rf"\b{re.escape(name)}(?:s|d|ed)?\b", re.IGNORECASE)
    out = []
    for m in pat.finditer(text):
        after = text[m.start(): m.start() + len(name) + _AFTER]
        cut = _SENTENCE_END.search(after, len(name) + 10)
        if cut:
            after = after[: cut.start() + 1]
        # The lookahead needs the hit's first letter to see a sentence start.
        lo = max(0, m.start() - _BEFORE)
        before = text[lo: m.start() + 1]
        ends = list(_SENTENCE_END.finditer(before))
        if ends:
            before = before[ends[-1].end(): -1]
        else:
            before = before[:-1]
            if lo > 0 and " " in before:
                before = before[before.index(" ") + 1:]  # drop the cut word
        out.append((before, after))
    return out


class Found:
    def __init__(self) -> None:
        self.min: float | None = None
        self.max: float | None = None
        self.unit: str | None = None
        self.evidence: dict[str, str] = {}

    def widen_min(self, v: float, snippet: str) -> None:
        if self.min is None or v < self.min:
            self.min, self.evidence["min"] = v, snippet

    def widen_max(self, v: float, snippet: str) -> None:
        if self.max is None or v > self.max:
            self.max, self.evidence["max"] = v, snippet

    def take_unit(self, u: str, snippet: str) -> None:
        if self.unit is None:
            self.unit, self.evidence["unit"] = _norm_unit(u), snippet


def search(doc: Document, field: FieldDef, expected_unit: str | None = None) -> Found:
    """Everything the text states about this field's unit and limits.
    `expected_unit` is the unit the model or the library gave the field;
    when neither did, the only acceptable unit is one printed in brackets
    right after the name, and no number is read until one is found."""
    f = Found()
    entry = _library_entry(field)
    windows = [w for name in _names_for(field, entry) for w in _windows(doc.text, name)]
    if expected_unit is None:
        for before, after in windows:
            m = _UNIT_NEAR.search(after[:60])
            if m:
                f.take_unit(m.group(1) or m.group(2), re.sub(r"\s+", " ", before + after).strip())
                expected_unit = f.unit
                break
        if expected_unit is None:
            return f
    for before, after in windows:
        snippet = re.sub(r"\s+", " ", before + after).strip()
        if not _read(f, after, snippet, expected_unit, last=False):
            _read(f, before, snippet, expected_unit, last=True)
        if f.unit is None:
            m = _UNIT_NEAR.search(after)
            if m and _same_unit(expected_unit, m.group(1) or m.group(2)):
                f.take_unit(m.group(1) or m.group(2), snippet)
    return f


def _pick(pat: re.Pattern, text: str, last: bool):
    """The statement nearest the name: first after it, last before it."""
    ms = list(pat.finditer(text))
    if not ms:
        return None
    return ms[-1] if last else ms[0]


def _read(f: Found, text: str, snippet: str, expected_unit: str | None, last: bool) -> bool:
    """Read one range or one-sided limit out of `text`. True if any was taken."""
    m = _pick(_RANGE, text, last)
    if m:
        lo, hi, unit = _num(m.group(1)), _num(m.group(2)), m.group(3)
        if lo < hi and _same_unit(expected_unit, unit):
            f.widen_min(lo, snippet)
            f.widen_max(hi, snippet)
            f.take_unit(unit, snippet)
            return True
    took = False
    m = _pick(_MIN, text, last)
    if m:
        v, unit = m.group(1) or m.group(3), m.group(2) or m.group(4)
        if _same_unit(expected_unit, unit):
            f.widen_min(_num(v), snippet)
            f.take_unit(unit, snippet)
            took = True
    m = _pick(_MAX, text, last)
    if m:
        v, unit = m.group(1) or m.group(3), m.group(2) or m.group(4)
        if _same_unit(expected_unit, unit):
            f.widen_max(_num(v), snippet)
            f.take_unit(unit, snippet)
            took = True
    return took


def complete(field: FieldDef) -> bool:
    """Nothing left for a reviewer to fill in."""
    if field.type in NUMERIC:
        has_unit = field.unit is not None or bool(_COUNT.search(field.name))
        return has_unit and field.min is not None and field.max is not None
    if field.type == "choice":
        return bool(field.choices)
    return True


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def fill(field: FieldDef, doc: Document) -> FieldDef:
    """Fill a numeric field's missing unit and limits from the protocol text.
    Clears the flag only when the unit was already known and nothing is
    left missing afterwards."""
    if field.type not in NUMERIC or field.issue not in ("none", "missing"):
        return field
    if complete(field):
        return field
    entry = _library_entry(field)
    expected = field.unit or (entry.get("unit") if entry else None)
    found = search(doc, field, expected)
    if found.min is not None and found.max is not None and found.min >= found.max:
        # Two statements that cannot both be bounds of the same field.
        return field
    filled: list[str] = []
    if field.unit is None and found.unit:
        field.unit = found.unit
        filled.append("unit")
    if field.min is None and found.min is not None:
        field.min = found.min
        filled.append("min")
    if field.max is None and found.max is not None:
        field.max = found.max
        filled.append("max")
    if not filled:
        return field
    field.suggested = [*field.suggested, *filled]
    field.suggested_from = "protocol"
    parts = []
    if "min" in filled or "max" in filled:
        parts.append(f"range {_fmt(field.min) if field.min is not None else '…'}"
                     f" to {_fmt(field.max) if field.max is not None else '…'}")
    if "unit" in filled:
        parts.append(f"unit {field.unit}")
    snippets = sorted({found.evidence[k] for k in filled if k in found.evidence})
    quoted = " / ".join(f"“{s}”" for s in snippets)
    note = f"Found in the protocol text: {', '.join(parts)}, from {quoted}."
    if field.issue == "missing" and expected is not None and complete(field):
        field.issue = "none"
        if field.status == "flagged":
            field.status = "draft"
        field.issue_note = note
    else:
        field.issue_note = ((field.issue_note or "").rstrip() + " " + note).strip()
    return field
