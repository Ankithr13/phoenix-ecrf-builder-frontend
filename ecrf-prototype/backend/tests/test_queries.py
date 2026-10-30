"""Stage 5: queries in both directions."""

from conftest import BGH, BUILDER, MRC, fresh_client, login
from sqlalchemy import select
from test_lock_sites_data import entry, lock_and_assign, site_client, sponsor_draft

from ecrf.storage import db
from ecrf.storage.models import ObservationHistory


def _setup():
    """A locked protocol assigned to both sites, one BGH value entered."""
    pid = sponsor_draft()
    approver = lock_and_assign(pid, "BGH", "MRC")
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects")
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130)).status_code == 200
    row = approver.get(f"/api/protocols/{pid}/data").json()[0]
    return pid, approver, bgh, row


def test_full_flow_raise_answer_with_correction_close_approve(client, demo_accounts):
    pid, approver, bgh, row = _setup()

    q = approver.post(f"/api/data/{row['id']}/queries", json={"text": "130 looks low for this patient, please check"}).json()
    assert q["status"] == "open" and q["observation_status"] == "queried"
    assert approver.post(f"/api/data/{row['id']}/queries", json={"text": "again"}).status_code == 409

    # Approval is blocked while the query is live.
    r = approver.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]})
    assert r.status_code == 409 and r.json()["detail"]["queried"] == [row["id"]]

    # The site sees it as an open item and answers with a corrected value.
    assert [x["id"] for x in bgh.get("/api/queries", params={"status": "open"}).json()] == [q["id"]]
    r = bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "transcription slip, it was 138", "new_value": 138})
    assert r.status_code == 200 and r.json()["status"] == "answered" and r.json()["value"] == "138.0"
    assert bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "x", "new_value": 9999}).status_code == 422

    hist = approver.get(f"/api/protocols/{pid}/data/{row['id']}/history").json()
    assert hist[-1]["old_value"] == "130.0" and hist[-1]["new_value"] == "138.0"
    assert hist[-1]["reason"].startswith(f"query {q['id']}:")
    with db.session() as s:
        assert s.scalars(select(ObservationHistory)).first().reason

    # Still blocked while answered; the sponsor must close it first.
    assert approver.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]}).status_code == 409
    assert [x["id"] for x in approver.get("/api/queries", params={"status": "answered"}).json()] == [q["id"]]
    r = approver.post(f"/api/queries/{q['id']}/close")
    assert r.status_code == 200 and r.json()["status"] == "closed" and r.json()["observation_status"] == "entered"

    assert approver.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]}).json() == {"approved": 1}
    final = approver.get(f"/api/protocols/{pid}/data").json()[0]
    assert final["status"] == "approved" and final["value"] == "138.0"
    assert bgh.get("/api/queries", params={"status": "open"}).json() == []


def test_a_site_cannot_answer_another_sites_query(client, demo_accounts):
    _, approver, bgh, row = _setup()
    q = approver.post(f"/api/data/{row['id']}/queries", json={"text": "check"}).json()
    mrc = site_client(MRC)
    assert mrc.get("/api/queries").json() == []
    assert mrc.post(f"/api/queries/{q['id']}/answer", json={"text": "not mine"}).status_code == 404
    assert bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "mine"}).status_code == 200


def test_queried_value_can_be_corrected_through_data_entry_too(client, demo_accounts):
    pid, approver, bgh, row = _setup()
    approver.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]})
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 135)).status_code == 409, "approved is frozen"
    approver.post(f"/api/data/{row['id']}/queries", json={"text": "please re-check"})
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 135)).status_code == 200, "open query reopens it"


def test_builder_can_raise_and_close_too(client, demo_accounts):
    _, _, _, row = _setup()
    builder = fresh_client()
    builder.__enter__()
    login(builder, BUILDER)
    q = builder.post(f"/api/data/{row['id']}/queries", json={"text": "unit?"}).json()
    assert builder.post(f"/api/queries/{q['id']}/close").json()["status"] == "closed"


def test_site_raises_sponsor_answers_site_closes(client, demo_accounts):
    _, sponsor, bgh, row = _setup()
    q = bgh.post(f"/api/data/{row['id']}/queries", json={"text": "Form says mmHg but our device reports kPa. Which do you want?"}).json()
    assert q["raised_by_org"] == "site" and q["status"] == "open" and q["observation_status"] == "queried"
    assert q["can_close"] is True and q["can_answer"] is False, "the site raised it, so the site closes it"
    # Not the site's turn to answer its own question.
    assert bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "me"}).status_code == 403
    # The sponsor sees it as waiting for them.
    mine = next(x for x in sponsor.get("/api/queries").json() if x["id"] == q["id"])
    assert mine["for_me"] is True and mine["can_answer"] is True and mine["can_close"] is False
    # A sponsor answers in words; it may not change the entered value.
    assert sponsor.post(f"/api/queries/{q['id']}/answer", json={"text": "x", "new_value": 120}).status_code == 403
    r = sponsor.post(f"/api/queries/{q['id']}/answer", json={"text": "mmHg, as on the form. Convert and re-enter."})
    assert r.status_code == 200 and r.json()["status"] == "answered"
    # Only the raiser closes.
    assert sponsor.post(f"/api/queries/{q['id']}/close").status_code == 403
    r = bgh.post(f"/api/queries/{q['id']}/close")
    assert r.status_code == 200 and r.json()["status"] == "closed" and r.json()["observation_status"] == "entered"
    # The other site cannot raise a query on a BGH value.
    assert site_client(MRC).post(f"/api/data/{row['id']}/queries", json={"text": "?"}).status_code == 404


def test_sponsor_raised_query_direction_is_unchanged(client, demo_accounts):
    _, sponsor, bgh, row = _setup()
    q = sponsor.post(f"/api/data/{row['id']}/queries", json={"text": "check"}).json()
    assert q["raised_by_org"] == "sponsor" and q["can_close"] and not q["can_answer"]
    assert sponsor.post(f"/api/queries/{q['id']}/answer", json={"text": "me"}).status_code == 403
    assert bgh.post(f"/api/queries/{q['id']}/close").status_code == 403
    assert bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "ok", "new_value": 131}).status_code == 200
    assert sponsor.post(f"/api/queries/{q['id']}/close").status_code == 200


def test_queries_about_a_study_a_patient_or_a_visit(client, demo_accounts):
    pid, sponsor, bgh, row = _setup()
    mrc = site_client(MRC)
    # Site asks about the study as a whole: no patient, no value.
    q = bgh.post("/api/queries", json={"protocol_id": pid, "text": "Which visit window applies to Week 4?"}).json()
    assert q["about"] == "study" and q["site"] == "BGH" and q["subject"] is None and q["value"] is None
    # Sponsor sees it, answers in words, cannot attach a value, site closes.
    assert any(x["id"] == q["id"] and x["for_me"] for x in sponsor.get("/api/queries").json())
    assert sponsor.post(f"/api/queries/{q['id']}/answer", json={"text": "x", "new_value": 1}).status_code == 403
    assert sponsor.post(f"/api/queries/{q['id']}/answer", json={"text": "Plus or minus 3 days."}).status_code == 200
    assert bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "ok", "new_value": 5}).status_code in (403, 422)
    assert bgh.post(f"/api/queries/{q['id']}/close").status_code == 200
    # The other site never sees BGH's study-level question.
    assert all(x["id"] != q["id"] for x in mrc.get("/api/queries").json())
    assert mrc.post(f"/api/queries/{q['id']}/answer", json={"text": "?"}).status_code == 404

    # Sponsor asks about a patient: belongs to that patient's site.
    q2 = sponsor.post("/api/queries", json={"protocol_id": pid, "subject_code": "bgh-001", "text": "Consent date?"}).json()
    assert q2["about"] == "patient" and q2["site"] == "BGH" and q2["subject"] == "BGH-001"
    assert any(x["id"] == q2["id"] for x in bgh.get("/api/queries").json())
    assert all(x["id"] != q2["id"] for x in mrc.get("/api/queries").json())
    # ... about a visit of a patient.
    q3 = sponsor.post("/api/queries", json={"protocol_id": pid, "subject_code": "BGH-001", "visit": "Week 4", "text": "Was Week 4 in window?"}).json()
    assert q3["about"] == "visit" and q3["visit"] == "Week 4"
    assert sponsor.post("/api/queries", json={"protocol_id": pid, "subject_code": "BGH-001", "visit": "Week 99", "text": "?"}).status_code == 422
    # A sponsor asking the study as a whole must name the site, and an assigned one.
    assert sponsor.post("/api/queries", json={"protocol_id": pid, "text": "no site"}).status_code == 422
    bgh_org = next(o["org_id"] for o in sponsor.get(f"/api/protocols/{pid}/sites").json() if o["code"] == "BGH")
    q4 = sponsor.post("/api/queries", json={"protocol_id": pid, "site_org_id": bgh_org, "text": "Enrolment update please"}).json()
    assert q4["about"] == "study" and q4["site"] == "BGH"
    # A query about one value through the general endpoint still marks the value.
    q5 = sponsor.post("/api/queries", json={"protocol_id": pid, "observation_id": row["id"], "text": "check"}).json()
    assert q5["about"] == "value" and q5["observation_status"] == "queried" and q5["field"] == row["field"]
    # Sites cannot ask about another site's patient.
    assert mrc.post("/api/queries", json={"protocol_id": pid, "subject_code": "BGH-001", "text": "?"}).status_code == 404
