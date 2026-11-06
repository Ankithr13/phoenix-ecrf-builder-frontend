from conftest import BUILDER, fresh_client, login
from test_lock_sites_data import sponsor_draft


def test_save_draft_preserves_undecided_status_and_is_resumable(client, demo_accounts):
    protocol_id = sponsor_draft(approve_everything=False)
    login(client, BUILDER)
    before = client.get(f"/api/protocols/{protocol_id}/draft").json()
    visit = next(form for form in before["draft"]["forms"]
                 if any(field["status"] == "draft" for field in form["fields"]))
    field = next(field for field in visit["fields"] if field["status"] == "draft")
    response = client.post(f"/api/protocols/{protocol_id}/review", json={
        "changes": [{"visit": visit["visit"], "name": field["name"],
                     "required": not field["required"]}],
        "note": "Pause review for clarification", "action": "save",
    })
    assert response.status_code == 200
    with fresh_client() as returning:
        login(returning, BUILDER)
        resumed = returning.get(f"/api/protocols/{protocol_id}/draft").json()
    assert resumed["version"] == before["version"] + 1
    assert resumed["state"] == "draft"
    assert resumed["note"] == "Pause review for clarification"
    assert resumed["lock_blockers"] == before["lock_blockers"]
    saved_visit = next(form for form in resumed["draft"]["forms"] if form["visit"] == visit["visit"])
    saved_field = next(item for item in saved_visit["fields"] if item["name"] == field["name"])
    assert saved_field["required"] is not field["required"]
    assert saved_field["status"] == "draft"
    assert client.post(f"/api/protocols/{protocol_id}/lock").status_code == 409
    assert not any(site["assigned"] for site in client.get(f"/api/protocols/{protocol_id}/sites").json())


def test_note_only_save_is_a_draft_not_an_approval(client, demo_accounts):
    protocol_id = sponsor_draft(approve_everything=False)
    login(client, BUILDER)
    before = client.get(f"/api/protocols/{protocol_id}/draft").json()
    response = client.post(f"/api/protocols/{protocol_id}/review", json={
        "changes": [], "note": "Continue tomorrow", "action": "save"})
    assert response.status_code == 200
    after = client.get(f"/api/protocols/{protocol_id}/draft").json()
    assert after["state"] == "draft"
    assert after["draft"]["forms"] == before["draft"]["forms"]
    assert after["lock_blockers"] == before["lock_blockers"]
    assert after["note"] == "Continue tomorrow"


def test_management_counts_follow_saved_decisions_not_extraction_summary(client, demo_accounts):
    protocol_id = sponsor_draft(approve_everything=False)
    login(client, BUILDER)
    before = client.get("/api/protocols").json()[0]
    assert before["review_blockers"]["draft"] > 0
    assert before["review_blockers"]["flagged"] > 0
    assert client.post(f"/api/protocols/{protocol_id}/review", json={
        "changes": [], "action": "approve_all_remaining"}).status_code == 200
    after = client.get("/api/protocols").json()[0]
    assert after["review_blockers"] == {"draft": 0, "flagged": 1}
    assert after["summary"] == before["summary"]
    assert after["state"] == "draft"


def test_all_decided_can_remain_draft_until_explicit_lock(client, demo_accounts):
    protocol_id = sponsor_draft(approve_everything=False)
    login(client, BUILDER)
    draft = client.get(f"/api/protocols/{protocol_id}/draft").json()["draft"]
    decisions = [{"visit": form["visit"], "name": field["name"], "status": "approved"}
                 for form in draft["forms"] for field in form["fields"]]
    assert client.post(f"/api/protocols/{protocol_id}/review", json={
        "changes": decisions, "action": "save"}).status_code == 200
    ready = client.get("/api/protocols").json()[0]
    assert ready["state"] == "draft"
    assert ready["review_blockers"] == {"draft": 0, "flagged": 0}
    assert client.post(f"/api/protocols/{protocol_id}/lock").status_code == 200
    assert client.get("/api/protocols").json()[0]["state"] == "locked"
    assert not any(site["assigned"] for site in client.get(f"/api/protocols/{protocol_id}/sites").json())
    assert client.post(f"/api/protocols/{protocol_id}/review", json={
        "changes": [], "action": "save"}).status_code == 409


def test_unextracted_protocol_has_no_review_counts(client, demo_accounts):
    login(client, BUILDER)
    assert client.post("/api/protocols/sample").status_code == 200
    protocol = client.get("/api/protocols").json()[0]
    assert protocol["latest_version"] is None
    assert protocol["review_blockers"] is None
