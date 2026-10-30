"""Values that follow from other values, computed in code.

A site enters weight and height; BMI follows. The form may carry a BMI
field because the protocol asks for it, and a person typing it in is the
usual source of a wrong BMI. So the frontend fills these in as the inputs
are typed and the server refuses a derived value that disagrees with its
inputs by more than a rounding tolerance.

The frontend mirrors these formulas in src/derive.ts. The server is the
guarantee; the mirror is for immediate feedback. Inputs are matched by
CDASH code first, then by name, so a protocol's own wording still works.
Units are converted where the form states them (lb, m, in); a missing
unit is taken as the CDASH default.
"""

import math
import re
from dataclasses import dataclass

from ecrf.schema import FieldDef

# What each derived quantity needs and how it is recognised.
# key -> (cdash codes, name regex)
INPUTS: dict[str, tuple[tuple[str, ...], str]] = {
    "weight": (("WEIGHT",), r"\b(body )?weight\b"),
    "height": (("HEIGHT",), r"\b(body )?height\b"),
    "sbp": (("SYSBP",), r"\bsystolic\b"),
    "dbp": (("DIABP",), r"\bdiastolic\b"),
    "hr": (("PULSE", "EGHR"), r"\b(heart rate|pulse)\b"),
    "qt": (("QT",), r"\bqt\b(?!c)|\bqt interval\b|\buncorrected qt\b"),
    "rr": (("RR",), r"\brr interval\b"),
    "creat": (("CREAT",), r"\b(serum )?creatinine\b"),
}
DERIVED: dict[str, tuple[tuple[str, ...], str]] = {
    "bmi": (("BMI",), r"\bbmi\b|body mass index"),
    "bsa": ((), r"\bbsa\b|body surface area"),
    "map": ((), r"\bmean arterial pressure\b|\bmap\b"),
    "pulse_pressure": ((), r"\bpulse pressure\b"),
    "qtcf": (("QTCF",), r"\bqtcf\b|fridericia"),
    "egfr": (("EGFR",), r"\begfr\b|glomerular filtration"),
}
TOLERANCE = {"bmi": 0.2, "bsa": 0.05, "map": 1.0, "pulse_pressure": 0.5, "qtcf": 5.0, "egfr": 2.0}
LABEL = {"bmi": "BMI", "bsa": "BSA", "map": "Mean arterial pressure", "pulse_pressure": "Pulse pressure",
         "qtcf": "QTcF", "egfr": "eGFR (CKD-EPI 2021)"}


@dataclass
class Derived:
    key: str
    value: float
    inputs: dict[str, float]
    unit: str


def role_of(field: FieldDef, table: dict) -> str | None:
    """Which input or derived quantity this field is, if any."""
    for key, (codes, _pat) in table.items():
        if field.cdash and field.cdash in codes:
            return key
    name = field.name.lower()
    for key, (_codes, pat) in table.items():
        if re.search(pat, name):
            return key
    return None


def _kg(v: float, unit: str | None) -> float:
    u = (unit or "kg").lower()
    return v * 0.45359237 if u in ("lb", "lbs", "pound", "pounds") else v


def _cm(v: float, unit: str | None) -> float:
    u = (unit or "cm").lower()
    if u in ("m", "metre", "metres", "meter", "meters"):
        return v * 100
    if u in ("in", "inch", "inches"):
        return v * 2.54
    return v


def _ms(v: float, unit: str | None) -> float:
    u = (unit or "ms").lower()
    return v * 1000 if u in ("s", "sec", "seconds", "second") else v


def _mgdl(v: float, unit: str | None) -> float:
    u = (unit or "mg/dl").lower()
    return v / 88.42 if u in ("umol/l", "µmol/l", "micromol/l") else v


def compute(values: dict[str, tuple[float, str | None]], birth_year: int | None = None,
            sex: str | None = None, year: int | None = None) -> list[Derived]:
    """`values` maps input key -> (value, unit as stated on the form)."""
    out: list[Derived] = []
    g = {k: v for k, (v, _) in values.items()}
    u = {k: unit for k, (_, unit) in values.items()}
    if "weight" in g and "height" in g:
        kg, cm = _kg(g["weight"], u["weight"]), _cm(g["height"], u["height"])
        if kg > 0 and cm > 0:
            out.append(Derived("bmi", round(kg / (cm / 100) ** 2, 1), {"weight": kg, "height": cm}, "kg/m2"))
            out.append(Derived("bsa", round(math.sqrt(cm * kg / 3600), 2), {"weight": kg, "height": cm}, "m2"))
    if "sbp" in g and "dbp" in g:
        s, d = g["sbp"], g["dbp"]
        out.append(Derived("map", round(d + (s - d) / 3, 1), {"sbp": s, "dbp": d}, "mmHg"))
        out.append(Derived("pulse_pressure", round(s - d, 1), {"sbp": s, "dbp": d}, "mmHg"))
    if "qt" in g and ("rr" in g or "hr" in g):
        qt = _ms(g["qt"], u["qt"])
        rr_s = _ms(g["rr"], u["rr"]) / 1000 if "rr" in g else 60 / g["hr"] if g["hr"] > 0 else None
        if rr_s and rr_s > 0:
            out.append(Derived("qtcf", round(qt / rr_s ** (1 / 3), 0), {"qt": qt, "rr_seconds": round(rr_s, 3)}, "ms"))
    if "creat" in g and birth_year and sex in ("Female", "Male") and year:
        age = year - birth_year
        scr = _mgdl(g["creat"], u["creat"])
        if scr > 0 and 0 < age < 130:
            kappa, alpha = (0.7, -0.241) if sex == "Female" else (0.9, -0.302)
            r = scr / kappa
            egfr = 142 * min(r, 1) ** alpha * max(r, 1) ** -1.2 * 0.9938 ** age * (1.012 if sex == "Female" else 1)
            out.append(Derived("egfr", round(egfr, 0), {"creatinine": scr, "age": age, "sex": sex}, "mL/min/1.73m2"))
    return out


def check(fields: dict[str, FieldDef], readings: list, birth_year: int | None = None,
          sex: str | None = None, year: int | None = None) -> dict[str, str]:
    """Errors for derived fields whose entered value disagrees with the
    inputs in the same submission. Keys are 'Field#repeat'."""
    inputs: dict[str, tuple[float, str | None]] = {}
    entered: dict[str, tuple[str, float]] = {}
    for r in readings:
        f = fields.get(r.field_name)
        if f is None or f.type not in ("integer", "decimal") or r.value in (None, ""):
            continue
        try:
            v = float(r.value)
        except (TypeError, ValueError):
            continue
        key = role_of(f, INPUTS)
        if key and r.repeat_num == 1 and key not in inputs:
            inputs[key] = (v, f.unit)
        dkey = role_of(f, DERIVED)
        if dkey and r.repeat_num == 1:
            entered[dkey] = (r.field_name, v)
    errors: dict[str, str] = {}
    if not entered:
        return errors
    for d in compute(inputs, birth_year, sex, year):
        if d.key in entered:
            name, v = entered[d.key]
            if abs(v - d.value) > TOLERANCE[d.key]:
                shown = ", ".join(f"{k} {val:g}" if isinstance(val, float) else f"{k} {val}" for k, val in d.inputs.items())
                errors[f"{name}#1"] = f"{LABEL[d.key]} from {shown} is {d.value:g}, not {v:g}"
    return errors
