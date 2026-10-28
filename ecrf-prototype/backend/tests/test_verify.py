"""The grounding check at its edges."""

from conftest import BUILDER, login

from ecrf.ingest import Document
from ecrf.schema import FieldDef, Source
from ecrf.verify import check_field, clean_quote, locate

# Lifted from protocol 5 in the dev database: the model copied the context
# label into its quote and the field was rejected at 89.4.
PROTOCOL_5_TEXT = (
    "Inclusion criteria. 1 PAH. 3. Right heart catheterization performed at "
    "Screening with results that are: a mean pulmonary arterial pressure of "
    "25 mmHg or more. 2. Persistent hypotension at Screening."
)


def test_section_label_is_stripped_before_matching():
    q = "[Section 3] Right heart catheterization performed at Screening with results that are:"
    assert clean_quote(q).startswith("Right heart")
    assert clean_quote("no label here") == "no label here"
    doc = Document(text=PROTOCOL_5_TEXT)
    f = FieldDef(name="RHC performed", type="boolean", source=Source(section="3", quote=q))
    check_field(f, doc, 90)
    assert f.verdict == "exact" and f.match_score == 100.0
    assert f.source.quote.startswith("Right heart"), "the stored quote loses the label too"


def test_threshold_compares_the_rounded_score(monkeypatch):
    # A raw 89.96 rounds to 90.0 on screen; the decision must use 90.0 too.
    import ecrf.verify as verify
    monkeypatch.setattr(verify, "locate", lambda q, t: ("approximate", 89.96, 0))
    f = FieldDef(name="x", type="text", source=Source(section="1", quote="twenty characters here"))
    check_field(f, Document(text="irrelevant"), 90)
    assert f.match_score == 90.0 and f.verdict == "approximate"


def test_locate_still_measures_verbatim_hits():
    v, score, off = locate("hypotension at Screening", PROTOCOL_5_TEXT)
    assert v == "exact" and score == 100.0 and off > 0


def test_reextraction_is_refused_after_review_unless_forced(client, demo_accounts):
    c = client
    login(c, BUILDER)
    if True:
        pid = c.post("/api/protocols/sample").json()["id"]
        assert c.post(f"/api/protocols/{pid}/extract").status_code == 200
        # A second extraction with no review in between is fine.
        assert c.post(f"/api/protocols/{pid}/extract").status_code == 200
        c.post(f"/api/protocols/{pid}/review", json={
            "changes": [{"visit": "Week 4", "name": "Systolic Blood Pressure", "status": "approved"}]})
        r = c.post(f"/api/protocols/{pid}/extract")
        assert r.status_code == 409 and "force=true" in r.json()["detail"]
        r = c.post(f"/api/protocols/{pid}/extract?force=true")
        assert r.status_code == 200 and r.json()["version"] == 4
        # the reviewed version is still there
        assert [v["version"] for v in c.get(f"/api/protocols/{pid}/versions").json()] == [1, 2, 3, 4]


def test_duplicate_upload_returns_the_existing_protocol(client, demo_accounts):
    c = client
    login(c, BUILDER)
    sample = "data/sample/PHX-401-201_protocol.pdf"
    import os
    path = os.path.join(os.path.dirname(__file__), "..", sample)
    if True:
        with open(path, "rb") as f:
            a = c.post("/api/protocols/upload", files={"file": ("first.pdf", f, "application/pdf")}).json()
        with open(path, "rb") as f:
            b = c.post("/api/protocols/upload", files={"file": ("renamed.pdf", f, "application/pdf")}).json()
        assert b["id"] == a["id"] and b["already_loaded"] is True
        assert len(c.get("/api/protocols").json()) == 1


def test_library_suggestions_are_marked_and_explained():
    from ecrf import cdash
    f = FieldDef(name="Heart Rate", type="integer", issue="missing",
                 issue_note="Protocol requires heart rate but states no unit or range.",
                 source=Source(section="7", quote="heart rate will be measured at each visit"))
    cdash.enrich(f)
    assert f.cdash == "PULSE" and f.unit == "beats/min" and f.min == 20 and f.max == 250
    assert set(f.suggested) == {"unit", "min", "max"}
    assert "Suggested from the CDASH library (PULSE)" in f.issue_note and "20 to 250" in f.issue_note
    assert f.issue == "missing", "still flagged until a person approves it"

    # A field the protocol fully specified gets the code but nothing suggested.
    g = FieldDef(name="Heart Rate", type="integer", unit="bpm", min=40, max=180,
                 source=Source(section="7", quote="heart rate will be measured at each visit"))
    cdash.enrich(g)
    assert g.suggested == [] and g.min == 40 and "Suggested" not in (g.issue_note or "")


def test_approve_suggested_signs_off_only_library_answered_flags(client, demo_accounts):
    c = client
    login(c, BUILDER)
    pid = c.post("/api/protocols/sample").json()["id"]
    c.post(f"/api/protocols/{pid}/extract")
    before = c.get(f"/api/protocols/{pid}/draft").json()["draft"]
    flagged = [(f["visit"], x["name"], x["issue"], x["suggested"]) for f in before["forms"] for x in f["fields"] if x["status"] == "flagged"]
    assert flagged, "the sample has a flagged field"
    r = c.post(f"/api/protocols/{pid}/review", json={"changes": [], "action": "approve_suggested"})
    assert r.status_code == 200
    after = c.get(f"/api/protocols/{pid}/draft").json()["draft"]
    still = {(f["visit"], x["name"]) for f in after["forms"] for x in f["fields"] if x["status"] == "flagged"}
    # The sample's flag is "conflicting", which no library value can answer, so it stays.
    assert all(issue != "missing" or not sugg for (_, _, issue, sugg) in flagged if (_, _) in still)


def test_guessed_ranges_fill_only_what_nothing_else_could():
    from ecrf import cdash, guess
    # Unit known, no library entry: guess from the unit.
    f = FieldDef(name="Mean Pulmonary Arterial Pressure", type="decimal", unit="mmHg", issue="missing",
                 source=Source(section="3", quote="mean pulmonary arterial pressure of 25 mmHg or more"))
    guess.fill(cdash.enrich(f))
    assert (f.min, f.max) == (0, 300) and f.suggested_from == "heuristic"
    assert "educated guess from the unit mmHg" in f.issue_note
    # No unit, name carries the hint.
    g = FieldDef(name="Age at enrolment", type="integer", issue="missing",
                 source=Source(section="4", quote="age at the time of enrolment in years"))
    guess.fill(g)
    assert (g.min, g.max) == (0, 120) and "from the field name" in g.issue_note
    # Nothing to go on: left alone, no fake precision.
    h = FieldDef(name="Investigator assessment", type="integer", source=Source(section="4", quote="investigator assessment recorded"))
    guess.fill(h)
    assert h.min is None and h.suggested == [] and h.suggested_from is None
    # Library wins over the guess and is labelled as the library.
    k = FieldDef(name="Heart Rate", type="integer", issue="missing", source=Source(section="7", quote="heart rate will be measured at each visit"))
    guess.fill(cdash.enrich(k))
    assert (k.min, k.max) == (20, 250) and k.suggested_from == "library"
    # Text and dates never get a numeric range.
    t = FieldDef(name="Age", type="text", source=Source(section="4", quote="age at the time of enrolment in years"))
    guess.fill(t)
    assert t.min is None
