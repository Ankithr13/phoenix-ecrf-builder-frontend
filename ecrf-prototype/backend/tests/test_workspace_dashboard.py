from datetime import datetime

from conftest import BGH, BUILDER, PASSWORD, login
from sqlalchemy import select

from ecrf.auth.passwords import hash_password
from ecrf.storage import db
from ecrf.storage.models import (
    ECRFVersion,
    Organisation,
    Protocol,
    Query,
    Study,
    StudyProtocol,
    User,
)

CREATED = datetime(2026, 1, 1)
REVIEWED = datetime(2026, 1, 2)
LOCKED = datetime(2026, 1, 3)


def add_protocol(session, org_id, name, study_id=None, states=()):
    protocol = Protocol(org_id=org_id, name=name, filename=f"{name}.pdf", text_hash=name,
                        normalised=name, sections=[], pages=1, tokens_estimate=1,
                        uploaded_by=BUILDER, uploaded_at=CREATED)
    session.add(protocol)
    session.flush()
    if study_id is not None:
        session.add(StudyProtocol(protocol_id=protocol.id, study_id=study_id,
                                  assigned_by=BUILDER, assigned_at=CREATED))
    for number, state in enumerate(states, start=1):
        session.add(ECRFVersion(protocol_id=protocol.id, protocol_hash=name,
                                version=number, state=state, content={}, created_by=BUILDER,
                                created_at=REVIEWED, locked_at=LOCKED if state == "locked" else None))
    return protocol


def test_workspace_dashboard_requires_a_sponsor_session(client, demo_accounts):
    assert client.get("/api/sponsor/dashboard").status_code == 401
    login(client, BGH)
    assert client.get("/api/sponsor/dashboard").status_code == 403


def test_empty_workspace_returns_real_zeros(client, demo_accounts):
    login(client, BUILDER)
    response = client.get("/api/sponsor/dashboard")
    assert response.status_code == 200
    assert response.json() == {"counts": {
        "studies": 0, "protocols": 0, "pending_reviews": 0, "queries_for_me": 0,
        "unassigned_protocols": 0, "unextracted_protocols": 0, "locked_protocols": 0,
    }, "studies": []}


def test_counts_use_latest_form_versions_and_include_unassigned_protocols(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        review = Study(org_id=organisation, code="REVIEW", name="Review study", created_by=BUILDER,
                       created_at=CREATED)
        empty = Study(org_id=organisation, code="EMPTY", name="Empty study", created_by=BUILDER,
                      created_at=CREATED)
        extraction = Study(org_id=organisation, code="EXTRACT", name="Extraction study", created_by=BUILDER,
                           created_at=CREATED)
        locked = Study(org_id=organisation, code="LOCKED", name="Locked study", created_by=BUILDER,
                       created_at=CREATED)
        session.add_all([review, empty, extraction, locked])
        session.flush()
        add_protocol(session, organisation, "Reviewed", review.id, ("draft", "locked"))
        add_protocol(session, organisation, "Draft", review.id, ("draft", "draft"))
        add_protocol(session, organisation, "Unassigned", states=("draft",))
        add_protocol(session, organisation, "Unextracted", extraction.id)
        add_protocol(session, organisation, "Locked", locked.id, ("locked",))
    data = client.get("/api/sponsor/dashboard").json()
    assert data["counts"] == {
        "studies": 4, "protocols": 5, "pending_reviews": 2, "queries_for_me": 0,
        "unassigned_protocols": 1, "unextracted_protocols": 1, "locked_protocols": 2,
    }
    rows = {study["code"]: study for study in data["studies"]}
    assert (rows["REVIEW"]["status"], rows["REVIEW"]["pending_reviews"],
            rows["REVIEW"]["locked_protocols"]) == ("needs_review", 1, 1)
    assert rows["REVIEW"]["latest_protocol_update"] == "2026-01-03T00:00:00Z"
    assert rows["EMPTY"]["status"] == "no_protocols"
    assert rows["EMPTY"]["latest_protocol_update"] is None
    assert rows["EXTRACT"]["status"] == "needs_extraction"
    assert rows["LOCKED"]["status"] == "forms_locked"
    assert [study["code"] for study in data["studies"]] == ["LOCKED", "REVIEW", "EXTRACT", "EMPTY"]


def test_queries_match_the_inbox_and_other_sponsors_are_excluded(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        study = Study(org_id=organisation, code="OWN", name="Own study", created_by=BUILDER)
        other = Organisation(name="Other sponsor", type="sponsor", code="OTHER")
        session.add_all([study, other])
        session.flush()
        session.add(Study(org_id=other.id, code="PRIVATE", name="Private study", created_by="other@example.demo"))
        own_protocol = add_protocol(session, organisation, "Own protocol", study.id)
        other_protocol = add_protocol(session, other.id, "Other protocol", states=("draft",))
        site = session.scalar(select(Organisation).where(Organisation.code == "BGH"))
        for side, status in (("site", "open"), ("sponsor", "answered"), ("sponsor", "open"),
                             ("site", "answered"), ("sponsor", "closed")):
            session.add(Query(protocol_id=own_protocol.id, site_org_id=site.id,
                              raised_by=BUILDER, raised_by_org=side, status=status, text="Synthetic question"))
        session.add(Query(protocol_id=other_protocol.id, site_org_id=site.id, raised_by=BGH,
                          raised_by_org="site", status="open", text="Other sponsor question"))
        session.add(User(email="dashboard@other.demo", name="Other Sponsor", org_id=other.id,
                         role="sponsor", password_hash=hash_password(PASSWORD), is_active=True))
    data = client.get("/api/sponsor/dashboard").json()
    assert data["counts"]["studies"] == 1
    assert data["counts"]["protocols"] == 1
    assert data["counts"]["queries_for_me"] == 2
    assert data["counts"]["queries_for_me"] == sum(query["for_me"] for query in client.get("/api/queries").json())
    assert [study["code"] for study in data["studies"]] == ["OWN"]
    login(client, "dashboard@other.demo")
    other_data = client.get("/api/sponsor/dashboard").json()
    assert other_data["counts"]["protocols"] == 1
    assert other_data["counts"]["queries_for_me"] == 1
    assert [study["code"] for study in other_data["studies"]] == ["PRIVATE"]


def test_dashboard_reflects_manual_reassignment(client, demo_accounts):
    login(client, BUILDER)
    first = client.post("/api/sponsor/studies", json={"code": "FIRST", "name": "First"}).json()
    second = client.post("/api/sponsor/studies", json={"code": "SECOND", "name": "Second"}).json()
    protocol = client.post("/api/protocols/sample", params={"study_id": first["id"]}).json()
    assert client.put(f"/api/protocols/{protocol['id']}/study", json={"study_id": second["id"]}).status_code == 200
    data = client.get("/api/sponsor/dashboard").json()
    rows = {study["id"]: study for study in data["studies"]}
    assert rows[first["id"]]["protocol_count"] == 0
    assert rows[first["id"]]["status"] == "no_protocols"
    assert rows[second["id"]]["protocol_count"] == 1
    assert rows[second["id"]]["status"] == "needs_extraction"
    assert data["counts"]["protocols"] == 1
    assert data["counts"]["unassigned_protocols"] == 0
