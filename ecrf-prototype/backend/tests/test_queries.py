"""Stage 5: the sponsor flags a value, the site answers, the sponsor closes."""

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
