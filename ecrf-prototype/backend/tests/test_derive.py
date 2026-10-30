"""Derived values: computed in code, checked on entry."""

from types import SimpleNamespace

from ecrf import derive
from ecrf.schema import FieldDef, Source

SRC = Source(section="7", quote="measured at every visit in the clinic")


def _f(name, unit=None, cdash=None, type="decimal"):
    return FieldDef(name=name, type=type, unit=unit, cdash=cdash, source=SRC)


def test_formulas():
    d = {x.key: x for x in derive.compute({"weight": (80, "kg"), "height": (175, "cm"), "sbp": (120, "mmHg"),
                                           "dbp": (80, "mmHg"), "qt": (400, "ms"), "hr": (60, "beats/min"),
                                           "creat": (1.0, "mg/dL")}, birth_year=1976, sex="Male", year=2026)}
    assert d["bmi"].value == 26.1 and d["bmi"].unit == "kg/m2"
    assert d["bsa"].value == 1.97
    assert d["map"].value == 93.3 and d["pulse_pressure"].value == 40
    assert d["qtcf"].value == 400, "at 60 bpm RR is 1 s so QTcF equals QT"
    assert 85 <= d["egfr"].value <= 95, d["egfr"].value   # CKD-EPI 2021, male, 50, Scr 1.0 -> about 90
    # Units stated on the form are honoured.
    e = {x.key: x for x in derive.compute({"weight": (176.4, "lb"), "height": (1.75, "m")})}
    assert e["bmi"].value == 26.1
    # Nothing derivable: nothing returned.
    assert derive.compute({"weight": (80, "kg")}) == []
    # eGFR needs birth year and sex from the registration.
    assert not [x for x in derive.compute({"creat": (1.0, "mg/dL")}) if x.key == "egfr"]


def test_roles_match_by_code_then_name():
    assert derive.role_of(_f("Weight", cdash="WEIGHT"), derive.INPUTS) == "weight"
    assert derive.role_of(_f("Body weight at visit"), derive.INPUTS) == "weight"
    assert derive.role_of(_f("Body Mass Index"), derive.DERIVED) == "bmi"
    assert derive.role_of(_f("QTcF Interval", cdash="QTCF"), derive.DERIVED) == "qtcf"
    assert derive.role_of(_f("QT Interval", cdash="QT"), derive.INPUTS) == "qt"
    assert derive.role_of(_f("Temperature"), derive.INPUTS) is None


def test_entered_bmi_must_agree_with_weight_and_height():
    fields = {"Weight": _f("Weight", "kg", "WEIGHT"), "Height": _f("Height", "cm", "HEIGHT"),
              "Body Mass Index": _f("Body Mass Index", "kg/m2", "BMI")}
    R = lambda n, v, rep=1: SimpleNamespace(field_name=n, value=v, repeat_num=rep)  # noqa: E731
    ok = derive.check(fields, [R("Weight", 80), R("Height", 175), R("Body Mass Index", 26.1)])
    assert ok == {}
    bad = derive.check(fields, [R("Weight", 80), R("Height", 175), R("Body Mass Index", 31)])
    assert bad == {"Body Mass Index#1": "BMI from weight 80, height 175 is 26.1, not 31"}
    # Without the inputs there is nothing to compare against.
    assert derive.check(fields, [R("Body Mass Index", 31)]) == {}
    # Repeats beyond the first are not used as inputs.
    assert derive.check(fields, [R("Weight", 80, 2), R("Height", 175), R("Body Mass Index", 31)]) == {}
