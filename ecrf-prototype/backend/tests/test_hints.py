"""The protocol text search that fills what the model left blank."""

from ecrf import cdash, guess, hints
from ecrf.ingest import Document
from ecrf.schema import FieldDef, Source

# Sentences lifted from test_protocol1 (NCT03541174) and test_protocol3
# (NCT02630316), the two places the model most often left gaps.
TEXT = (
    "Subjects aged 18 to 75 years inclusive with a seated systolic blood pressure of "
    "140 to 159 mmHg at Screening, who provide written informed consent. "
    "Blood pressure is measured in triplicate at intervals of 1 to 2 minutes and each "
    "reading recorded individually. Systolic values outside 60 to 250 mmHg and diastolic "
    "values outside 30 to 150 mmHg must be re-confirmed before the visit is closed. "
    "Vital signs must be assessed following at least 5 minutes of rest; collected prior "
    "to 6MWT; including weight, RR, HR, SBP, DBP, and temperature. "
    "Subjects must walk at least 150 meters on the practice 6-minute walk test. "
    "Treatment continues from Week 4 to Week 16 with visits in sections 3 to 5. "
    "Body weight (kg) is recorded at every visit. Bleeding time (seconds) is recorded at Screening. "
    "Blood for NT-proBNP must be drawn 10 to 60 minutes after dosing and prior to the 6MWT. "
    "Pulmonary function tests will be recorded as absolute values and % predicted: FEV1, FVC, TLC. "
    "Relative contraindications to exercise testing include a resting heart rate of more than 120 "
    "beats/min, a systolic BP of more than 180 mm Hg or less than 90 mm Hg at rest."
)
CONTRA = Document(text=TEXT.split("Relative contraindications")[1])
DOC = Document(text=TEXT)


def _f(name, unit=None, lo=None, hi=None, type="decimal", issue="missing", note="Protocol states no range."):
    return FieldDef(name=name, type=type, unit=unit, min=lo, max=hi, issue=issue, issue_note=note,
                    status="flagged" if issue != "none" else "draft",
                    source=Source(section="7", quote="measured at every visit in the clinic"))


def test_widest_stated_range_is_taken_and_the_flag_cleared():
    f = _f("Systolic Blood Pressure", unit="mmHg")
    hints.fill(f, DOC)
    # Eligibility says 140 to 159, the re-confirmation rule says 60 to 250. The
    # validation range must admit every legitimate value, so the wider one wins.
    assert (f.min, f.max) == (60, 250)
    assert f.suggested == ["min", "max"] and f.suggested_from == "protocol"
    assert f.issue == "none" and f.status == "draft", "the protocol states it, so nothing is missing"
    assert "Found in the protocol text: range 60 to 250" in f.issue_note
    assert "outside 60 to 250 mmHg" in f.issue_note, "the sentence it came from is shown"


def test_first_statement_only_so_the_diastolic_limits_do_not_leak():
    # "Systolic values outside 60 to 250 mmHg and diastolic values outside 30 to 150 mmHg"
    # is one sentence; the systolic field must not become 30 to 250.
    f = _f("Systolic Blood Pressure", unit="mmHg")
    hints.fill(f, DOC)
    assert f.min == 60
    d = _f("Diastolic Blood Pressure", unit="mmHg")
    hints.fill(d, DOC)
    assert (d.min, d.max) == (30, 150)


def test_statement_in_another_unit_is_ignored():
    # The heart rate paragraph says "at least 5 minutes of rest". The library
    # knows heart rate is in beats/min, so 5 minutes is not a minimum heart rate.
    f = _f("Heart Rate", type="integer")
    hints.fill(f, DOC)
    assert f.min is None and f.unit is None and f.suggested == []
    assert f.issue == "missing"


def test_one_sided_limit_fills_one_side_and_keeps_the_flag():
    f = _f("Practice 6-Minute Walk Distance", type="integer", unit="meters")
    hints.fill(f, DOC)
    assert f.min == 150 and f.max is None
    assert f.suggested == ["min"] and f.suggested_from == "protocol"
    assert f.issue == "missing", "max is still missing, so a person still decides"
    assert f.issue_note.startswith("Protocol states no range."), "the model's note is kept"
    # The guess then closes the gap and the field is labelled as guessed.
    guess.fill(cdash.enrich(f))
    assert f.max == 1000 and f.suggested_from == "heuristic"


def test_numbers_without_a_unit_are_never_limits():
    f = _f("Week", type="integer", unit="weeks")
    hints.fill(f, DOC)
    assert f.min is None and f.max is None, '"Week 4 to Week 16" is not a range'
    g = _f("Sections", type="integer")
    hints.fill(g, DOC)
    assert g.min is None


def test_unit_in_brackets_after_the_name():
    # The library says weight is in kg and the protocol says "(kg)": two
    # sources agree, nothing is missing, the flag goes.
    f = _f("Body weight", lo=2, hi=300)
    hints.fill(f, DOC)
    assert f.unit == "kg" and f.suggested == ["unit"] and f.suggested_from == "protocol"
    assert f.issue == "none"
    assert "Week 4" not in f.issue_note, "only the sentence with the hit is quoted"
    # Nobody knew the unit beforehand, so the search cannot vouch for what it
    # found and the flag stays for a person.
    g = _f("Bleeding time", lo=0, hi=600)
    hints.fill(g, DOC)
    assert g.unit == "seconds" and g.suggested_from == "protocol"
    assert g.issue == "missing"


def test_range_found_for_an_age_in_years():
    f = _f("Age", type="integer", unit="years")
    hints.fill(f, DOC)
    assert (f.min, f.max) == (18, 75) and f.issue == "none"


def test_untouched_when_the_protocol_says_nothing_or_the_field_is_not_numeric():
    # The text says NT-proBNP is "drawn 10 to 60 minutes after dosing". Nobody
    # knows the analyte's unit, so no number is read: 10 to 60 minutes is a
    # timing rule, not a concentration range. (Seen on the 76-page protocol.)
    f = _f("NT-proBNP Concentration")
    hints.fill(f, DOC)
    assert f.min is None and f.unit is None and f.suggested == [] and f.issue == "missing"
    # Even when the model gave a unit, a statement in another unit is not read.
    g = _f("NT-proBNP", unit="pg/mL")
    hints.fill(g, DOC)
    assert g.min is None and g.suggested == []
    b = _f("Urine Pregnancy Test Performed", type="boolean")
    hints.fill(b, DOC)
    assert b.suggested == [] and b.issue == "missing"
    c = _f("Systolic Blood Pressure", unit="mmHg", issue="ambiguous", note="Two conflicting limits.")
    hints.fill(c, DOC)
    assert c.min is None, "ambiguous and conflicting flags are a person's call"


def test_exclusion_thresholds_are_not_a_range():
    # "more than 180 mm Hg or less than 90 mm Hg" is a danger zone, not the
    # field's bounds. Read as bounds it gave a 75-page protocol a systolic
    # range of 180 to 90. Neither phrasing is read, and if two statements
    # ever cross (min above max) nothing is filled.
    f = _f("Systolic Blood Pressure", unit="mmHg")
    hints.fill(f, CONTRA)
    assert f.min is None and f.max is None and f.suggested == [] and f.issue == "missing"
    g = _f("Heart Rate", type="integer", unit="beats/min")
    hints.fill(g, CONTRA)
    assert g.min is None and g.max is None


def test_guess_fills_unit_and_the_missing_side():
    # No unit, no library entry: the unit comes from the name, the range from the unit.
    f = _f("NT-proBNP Concentration")
    guess.fill(cdash.enrich(f))
    assert f.unit == "pg/mL" and (f.min, f.max) == (0, 100000)
    assert set(f.suggested) == {"unit", "min", "max"} and f.suggested_from == "heuristic"
    assert "Range 0 to 100000, unit pg/mL is an educated guess from the field name," in f.issue_note
    # Only the upper limit missing: the lower one the model gave is kept.
    g = _f("Supplemental Oxygen Requirement at Rest", unit="L/min", lo=0)
    guess.fill(g)
    assert (g.min, g.max) == (0, 60) and g.suggested == ["max"]
    assert "from the unit L/min" in g.issue_note
    # A unit nobody recognises: the range comes from the unit the name implies.
    k = _f("FEV1", unit="L and % predicted")
    guess.fill(k)
    assert (k.min, k.max) == (0, 50) and k.suggested == ["min", "max"] and "from the field name" in k.issue_note
    m = _f("DLCO", unit="% predicted")
    guess.fill(m)
    assert (m.min, m.max) == (0, 300), "percent of predicted can exceed 100"
    # Everything the model gave stays and nothing is marked.
    h = _f("Heart Rate", type="integer", unit="bpm", lo=40, hi=180, issue="none", note=None)
    guess.fill(h)
    assert h.suggested == [] and h.suggested_from is None


def test_pipeline_order_protocol_then_library_then_guess():
    from ecrf.pipeline import _enrich
    # Protocol text answers everything: label is "protocol" and the flag is gone.
    a = _f("Systolic Blood Pressure", unit="mmHg")
    _enrich(a, DOC)
    assert a.suggested_from == "protocol" and a.status == "draft" and a.cdash == "SYSBP"
    # Protocol silent, library answers: label is "library", flag stays.
    b = _f("Potassium")
    _enrich(b, DOC)
    assert b.unit == "mEq/L" and (b.min, b.max) == (1.5, 9) and b.suggested_from == "library"
    assert b.status == "flagged"
    # Nobody but the guess: label is "heuristic", flag stays.
    c = _f("DLCO Absolute")
    _enrich(c, DOC)
    assert c.unit == "mL/min/mmHg" and (c.min, c.max) == (0, 100) and c.suggested_from == "heuristic"
    assert c.status == "flagged"
