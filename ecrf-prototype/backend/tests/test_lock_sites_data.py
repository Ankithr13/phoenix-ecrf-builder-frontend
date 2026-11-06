"""Stage 3: the form lock, site assignment, patients, and the approval gate."""

from conftest import APPROVER, BGH, BUILDER, MRC, fresh_client, login
from sqlalchemy import select

from ecrf.storage import db
from ecrf.storage.models import ObservationHistory, Organisation

SBP = "Systolic Blood Pressure"


def _org_id(code: str) -> int:
    with db.session() as s:
        return s.scalars(select(Organisation).where(Organisation.code == code)).first().id


def sponsor_draft(approve_everything: bool = True) -> int:
    """Builder loads the sample, extracts, and approves every draft field.
    The one flagged field is left for the approver."""
    c = fresh_client()
    with c:
        login(c, BUILDER)
        pid = c.post("/api/protocols/sample").json()["id"]
        assert c.post(f"/api/protocols/{pid}/extract").status_code == 200
        if approve_everything:
            c.post(f"/api/protocols/{pid}/review", json={"changes": [], "action": "approve_all_remaining"})
    return pid


def lock_and_assign(pid: int, *sites: str):
    """The builder decides the flagged field; the data manager locks and
    assigns. Returns the data manager's client."""
    builder = fresh_client()
    with builder:
        login(builder, BUILDER)
        builder.post(f"/api/protocols/{pid}/review", json={
            "changes": [{"visit": "Week 4", "name": SBP, "status": "approved"}]})
    c = fresh_client()
    c.__enter__()
    login(c, APPROVER)
    assert c.post(f"/api/protocols/{pid}/lock").status_code == 200
    for code in sites:
        assert c.post(f"/api/protocols/{pid}/sites", json={"site_org_id": _org_id(code)}).status_code == 200
    return c


def add_endpoint(dm, pid: int) -> dict:
    """One row of the statistical analysis plan: systolic, Day 1 to Week 12."""
    forms = dm.get(f"/api/protocols/{pid}/draft").json()["draft"]["forms"]
    field_id = next(f["field_id"] for form in forms if form["visit"] == "Day 1" for f in form["fields"] if f["name"] == SBP)
    r = dm.post(f"/api/protocols/{pid}/sap", json={"label": "Change in systolic BP", "kind": "endpoint", "field_id": field_id,
                                                   "baseline_visit_id": "Day 1", "analysis_visit_id": "Week 12", "unit": "mmHg"})
    assert r.status_code == 200, r.text
    return r.json()


def site_client(email: str):
    c = fresh_client()
    c.__enter__()
    login(c, email)
    return c


def entry(pid, subject, value, visit="Week 4", field=SBP, reason=None):
    return {"protocol_id": pid, "subject_id": subject, "visit": visit, "reason": reason,
            "readings": [{"field_name": field, "value": value}]}


def submit(c, pid, subject, visit="Week 4"):
    r = c.post("/api/data/submit", json={"protocol_id": pid, "subject_id": subject, "visit": visit})
    assert r.status_code == 200, r.text
    return r.json()


def people(rows):
    """Queries raised by a person, leaving out what the edit checks raised."""
    return [q for q in rows if q["raised_by"] != "system"]


# ------------------------------------------------------------------ lock

def test_lock_needs_every_field_decided_and_then_freezes_the_form(client, demo_accounts):
    pid = sponsor_draft()
    login(client, APPROVER)
    r = client.post(f"/api/protocols/{pid}/lock")
    assert r.status_code == 409 and "1 flagged" in r.json()["detail"]
    assert client.get(f"/api/protocols/{pid}/draft").json()["lock_blockers"] == {"draft": 0, "flagged": 1}

    builder = site_client(BUILDER)
    builder.post(f"/api/protocols/{pid}/review", json={
        "changes": [{"visit": "Week 4", "name": SBP, "status": "approved"}]})
    r = client.post(f"/api/protocols/{pid}/lock")
    assert r.status_code == 200 and r.json()["locked_by"] == APPROVER
    d = client.get(f"/api/protocols/{pid}/draft").json()
    assert d["state"] == "locked" and d["locked_at"]

    # Nothing changes a locked form.
    r = builder.post(f"/api/protocols/{pid}/review", json={"changes": []})
    assert r.status_code == 409 and "locked" in r.json()["detail"].lower()
    assert builder.post(f"/api/protocols/{pid}/extract").status_code == 409
    assert builder.post(f"/api/protocols/{pid}/extract?force=true").status_code == 409
    assert client.get("/api/protocols").json()[0]["state"] == "locked"


def test_site_staff_cannot_lock(client, demo_accounts):
    pid = sponsor_draft()
    login(client, BGH)
    assert client.post(f"/api/protocols/{pid}/lock").status_code == 403


# ----------------------------------------------------------------- sites

def test_sites_see_only_assigned_locked_studies(client, demo_accounts):
    pid = sponsor_draft()
    login(client, APPROVER)
    r = client.post(f"/api/protocols/{pid}/sites", json={"site_org_id": _org_id("BGH")})
    assert r.status_code == 409, "assignment needs a locked form"
    bgh = site_client(BGH)
    assert bgh.get("/api/studies").json() == []

    lock_and_assign(pid, "BGH")
    studies = bgh.get("/api/studies").json()
    assert [x["id"] for x in studies] == [pid] and "Week 4" in studies[0]["visits"]
    assert bgh.get(f"/api/protocols/{pid}/draft").status_code == 200

    mrc = site_client(MRC)
    assert mrc.get("/api/studies").json() == []
    assert mrc.get(f"/api/protocols/{pid}/draft").status_code == 404

    sites = client.get(f"/api/protocols/{pid}/sites").json()
    assert {x["code"]: x["assigned"] for x in sites} == {"BGH": True, "MRC": False}


# -------------------------------------------------------------- subjects

def test_subject_codes_are_made_by_the_server_and_owned_by_the_site(client, demo_accounts):
    pid = sponsor_draft()
    lock_and_assign(pid, "BGH", "MRC")
    bgh, mrc = site_client(BGH), site_client(MRC)
    assert bgh.post(f"/api/studies/{pid}/subjects").json()["code"] == "BGH-001"
    assert bgh.post(f"/api/studies/{pid}/subjects").json()["code"] == "BGH-002"
    assert mrc.post(f"/api/studies/{pid}/subjects").json()["code"] == "MRC-001"

    assert [x["code"] for x in bgh.get(f"/api/studies/{pid}/subjects").json()] == ["BGH-001", "BGH-002"]
    assert [x["code"] for x in mrc.get(f"/api/studies/{pid}/subjects").json()] == ["MRC-001"]
    # MRC addressing a BGH patient: 404, not 403.
    assert mrc.post("/api/data/enter", json=entry(pid, "BGH-001", 130)).status_code == 404
    assert mrc.post("/api/data/validate", json=entry(pid, "BGH-001", 130)).status_code == 404
    # The data manager sees everyone.
    login(client, APPROVER)
    assert len(client.get(f"/api/studies/{pid}/subjects").json()) == 3


def test_site_cannot_enter_against_an_unlocked_form(client, demo_accounts):
    pid = sponsor_draft()                      # extracted, approved, not locked
    bgh = site_client(BGH)
    assert bgh.post(f"/api/studies/{pid}/subjects").status_code == 404
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130)).status_code == 404


# ------------------------------------------------------------ approval gate

def test_edits_write_history_and_approved_values_are_frozen(client, demo_accounts):
    pid = sponsor_draft()
    approver = lock_and_assign(pid, "BGH")
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects")

    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130)).json() == {"saved": 1}
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 135)).json() == {"saved": 1}
    r = bgh.post("/api/data/enter", json=entry(pid, "BGH-001", "abc"))
    assert r.status_code == 422, "a word in a number field is still refused"
    assert approver.get(f"/api/protocols/{pid}/data").json() == [], "a draft is the site's own"
    submit(bgh, pid, "BGH-001")

    rows = approver.get(f"/api/protocols/{pid}/data").json()
    assert len(rows) == 1 and rows[0]["value"] == "135" and rows[0]["status"] == "submitted"
    assert rows[0]["site"] == "BGH" and rows[0]["entered_by"] == BGH
    hist = approver.get(f"/api/protocols/{pid}/data/{rows[0]['id']}/history").json()
    assert [(h["old_value"], h["new_value"], h["changed_by"]) for h in hist] == [("130", "135", BGH)]
    with db.session() as s:
        assert s.scalar(select(ObservationHistory.id)) is not None

    assert approver.post(f"/api/protocols/{pid}/data/approve",
                         json={"observation_ids": [rows[0]["id"]]}).json() == {"approved": 1}
    r = bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 140, reason="a good reason"))
    assert r.status_code == 409 and r.json()["detail"]["approved"] == [f"{SBP}#1"]
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 135)).status_code == 200, "unchanged is no change"
    rows = approver.get(f"/api/protocols/{pid}/data", params={"status": "approved"}).json()
    assert rows[0]["value"] == "135" and rows[0]["approved_by"] == APPROVER


def test_stats_count_only_approved_rows_in_both_implementations(client, demo_accounts):
    pid = sponsor_draft()
    approver = lock_and_assign(pid, "BGH", "MRC")
    assert approver.post(f"/api/data/seed/{pid}").json()["already"] is False
    add_endpoint(approver, pid)
    dash = approver.get(f"/api/dashboard/{pid}").json()
    assert dash["data"]["readings"] == 0 < dash["data"]["entered_total"], "nothing seeded is approved"

    # Approving a subset moves both implementations together.
    pending = [r["id"] for r in approver.get(f"/api/protocols/{pid}/data", params={"status": "submitted"}).json()]
    approver.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": pending[::2]})
    dash = approver.get(f"/api/dashboard/{pid}").json()
    assert 0 < dash["data"]["readings"] < dash["data"]["entered_total"]
    assert all(st["pass"] for st in dash["stats"]), "app and independent results must agree on approved rows"
    before = dash["data"]["readings"]

    # Approving the rest changes both implementations the same way.
    approver.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": pending[1::2]})
    dash = approver.get(f"/api/dashboard/{pid}").json()
    assert dash["data"]["readings"] == dash["data"]["entered_total"] > before
    assert all(st["pass"] for st in dash["stats"])

    # The seeded subjects are real rows owned by the two demo sites.
    rows = approver.get(f"/api/protocols/{pid}/data", params={"site": "MRC"}).json()
    assert rows and all(r["subject"].startswith("MRC-") for r in rows)


def test_patient_registration_details_and_rules(client, demo_accounts):
    pid = sponsor_draft()
    sponsor = lock_and_assign(pid, "BGH")
    bgh = site_client(BGH)
    # Full registration; the code always comes from the server.
    r = bgh.post(f"/api/studies/{pid}/subjects", json={
        "birth_year": 1975, "sex": "Female", "enrolled_on": "2026-10-01", "note": "screened at clinic B"})
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["code"] == "BGH-001" and row["birth_year"] == 1975
    assert row["sex"] == "Female" and row["enrolled_on"] == "2026-10-01" and row["note"] == "screened at clinic B"
    # Empty body still works and the server numbers it.
    assert bgh.post(f"/api/studies/{pid}/subjects").json()["code"] == "BGH-002"
    # Rules.
    assert bgh.post(f"/api/studies/{pid}/subjects", json={"code": "BGH-0101"}).status_code == 422, "no typed codes"
    assert bgh.post(f"/api/studies/{pid}/subjects", json={"birth_year": 1850}).status_code == 422
    assert bgh.post(f"/api/studies/{pid}/subjects", json={"sex": "F"}).status_code == 422
    assert bgh.post(f"/api/studies/{pid}/subjects", json={"enrolled_on": "2099-01-01"}).status_code == 422
    assert bgh.post(f"/api/studies/{pid}/subjects", json={"enrolled_on": "01/10/2026"}).status_code == 422
    # Listed with the details, to the site and to the sponsor.
    codes = {x["code"]: x for x in bgh.get(f"/api/studies/{pid}/subjects").json()}
    assert codes["BGH-001"]["birth_year"] == 1975 and codes["BGH-002"]["birth_year"] is None
    assert {x["code"] for x in sponsor.get(f"/api/studies/{pid}/subjects").json()} >= {"BGH-001", "BGH-002"}


def test_an_unanswered_yes_no_is_not_a_no():
    """Seen in the UI: a lone 'Yes' checkbox meant an untouched required
    question was saved as False. A blank stays a blank: nothing is stored, and
    the required check notices it at submit."""
    from ecrf.api.data import _split, validate
    from ecrf.schema import FieldDef, Source
    f = FieldDef(name="Informed Consent Obtained", type="boolean", required=True,
                 source=Source(section="4", quote="written informed consent must be obtained"))
    assert validate(f, None) is None and _split(f, None) == (None, None)
    assert validate(f, "") is None and _split(f, "") == (None, None)
    assert validate(f, False) is None, "an explicit No is an answer"
    assert _split(f, False) == (None, "No")
    assert validate(f, True) is None
    assert validate(f, "maybe") == "must be yes or no"


def test_value_rules_dates_booleans_and_display():
    from ecrf.api.data import _split, as_bool, validate
    from ecrf.schema import FieldDef, Source
    src = Source(section="4", quote="recorded at every visit in the clinic")
    d = FieldDef(name="Visit Date", type="date", source=src)
    assert validate(d, "2026-10-01") is None
    assert validate(d, "01/10/2026") == "must be a date, YYYY-MM-DD"
    assert validate(d, "1850-01-01") == "date is out of range"
    n = FieldDef(name="Heart Rate", type="integer", min=20, max=250, source=src)
    assert validate(n, True) == "must be a number", "a boolean is not an integer 1"
    assert validate(n, "nan") == "must be a number"
    b = FieldDef(name="ECG Performed", type="boolean", source=src)
    for v in (True, "true", "Yes", "y", 1):
        assert as_bool(v) is True and _split(b, v) == (None, "Yes")
    for v in (False, "false", "No", "0"):
        assert as_bool(v) is False and _split(b, v) == (None, "No")
    assert _split(n, "138") == (138.0, None)
