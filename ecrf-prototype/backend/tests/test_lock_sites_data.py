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
    c = fresh_client()
    c.__enter__()
    login(c, APPROVER)
    c.post(f"/api/protocols/{pid}/review", json={
        "changes": [{"visit": "Week 4", "name": SBP, "status": "approved"}]})
    assert c.post(f"/api/protocols/{pid}/lock").status_code == 200
    for code in sites:
        assert c.post(f"/api/protocols/{pid}/sites", json={"site_org_id": _org_id(code)}).status_code == 200
    return c


def site_client(email: str):
    c = fresh_client()
    c.__enter__()
    login(c, email)
    return c


def entry(pid, subject, value, visit="Week 4", field=SBP):
    return {"protocol_id": pid, "subject_id": subject, "visit": visit,
            "readings": [{"field_name": field, "value": value}]}


# ------------------------------------------------------------------ lock

def test_lock_needs_every_field_decided_and_then_freezes_the_form(client, demo_accounts):
    pid = sponsor_draft()
    login(client, APPROVER)
    r = client.post(f"/api/protocols/{pid}/lock")
    assert r.status_code == 409 and "1 flagged" in r.json()["detail"]
    assert client.get(f"/api/protocols/{pid}/draft").json()["lock_blockers"] == {"draft": 0, "flagged": 1}

    client.post(f"/api/protocols/{pid}/review", json={
        "changes": [{"visit": "Week 4", "name": SBP, "status": "approved"}]})
    r = client.post(f"/api/protocols/{pid}/lock")
    assert r.status_code == 200 and r.json()["locked_by"] == APPROVER
    d = client.get(f"/api/protocols/{pid}/draft").json()
    assert d["state"] == "locked" and d["locked_at"]

    # Nothing changes a locked form.
    r = client.post(f"/api/protocols/{pid}/review", json={"changes": []})
    assert r.status_code == 409 and "locked" in r.json()["detail"].lower()
    assert client.post(f"/api/protocols/{pid}/extract").status_code == 409
    assert client.post(f"/api/protocols/{pid}/extract?force=true").status_code == 409
    assert client.get("/api/protocols").json()[0]["state"] == "locked"


def test_builder_cannot_lock(client, demo_accounts):
    pid = sponsor_draft()
    login(client, BUILDER)
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
    # The sponsor sees everyone.
    login(client, BUILDER)
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
    r = bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 9999))
    assert r.status_code == 422, "range check still applies"

    rows = approver.get(f"/api/protocols/{pid}/data").json()
    assert len(rows) == 1 and rows[0]["value"] == "135.0" and rows[0]["status"] == "entered"
    assert rows[0]["site"] == "BGH" and rows[0]["entered_by"] == BGH
    hist = approver.get(f"/api/protocols/{pid}/data/{rows[0]['id']}/history").json()
    assert [(h["old_value"], h["new_value"], h["changed_by"]) for h in hist] == [("130.0", "135.0", BGH)]
    with db.session() as s:
        assert s.scalar(select(ObservationHistory.id)) is not None

    assert approver.post(f"/api/protocols/{pid}/data/approve",
                         json={"observation_ids": [rows[0]["id"]]}).json() == {"approved": 1}
    r = bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 140))
    assert r.status_code == 409 and r.json()["detail"]["approved"] == [f"{SBP}#1"]
    rows = approver.get(f"/api/protocols/{pid}/data", params={"status": "approved"}).json()
    assert rows[0]["value"] == "135.0" and rows[0]["approved_by"] == APPROVER


def test_stats_count_only_approved_rows_in_both_implementations(client, demo_accounts):
    pid = sponsor_draft()
    login(client, BUILDER)
    assert client.post(f"/api/data/seed/{pid}").json()["already"] is False
    dash = client.get(f"/api/dashboard/{pid}").json()
    assert 0 < dash["data"]["readings"] < dash["data"]["entered_total"]
    assert all(st["pass"] for st in dash["stats"]), "app and independent results must agree on approved rows"
    before = dash["data"]["readings"]

    # Approving the rest changes both implementations the same way.
    login(client, APPROVER)
    pending = [r["id"] for r in client.get(f"/api/protocols/{pid}/data", params={"status": "entered"}).json()]
    client.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": pending})
    dash = client.get(f"/api/dashboard/{pid}").json()
    assert dash["data"]["readings"] == dash["data"]["entered_total"] > before
    assert all(st["pass"] for st in dash["stats"])

    # The seeded subjects are real rows owned by the two demo sites.
    rows = client.get(f"/api/protocols/{pid}/data", params={"site": "MRC"}).json()
    assert rows and all(r["subject"].startswith("MRC-") for r in rows)
