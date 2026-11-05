import pytest
from alembic import command
from conftest import BGH, BUILDER, MRC, PASSWORD, SPONSOR2, login
from sqlalchemy import create_engine, func, inspect, select
from test_ecrf_status import add_protocol, add_subject, reading

from ecrf.auth.passwords import hash_password
from ecrf.storage import db, migrate
from ecrf.storage.models import (
    ECRFVersion,
    HospitalSubmission,
    Notification,
    NotificationRead,
    Observation,
    Organisation,
    Protocol,
    ProtocolSite,
    Query,
    User,
)


@pytest.fixture
def assigned(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        sites = {site.code: site for site in session.scalars(select(Organisation).where(Organisation.type == "site"))}
        protocol, version = add_protocol(session, organisation)
        for site in sites.values():
            session.add(ProtocolSite(protocol_id=protocol.id, site_org_id=site.id, assigned_by=BUILDER))
        subject = add_subject(session, protocol, sites["BGH"], "BGH-001")
        observation = reading(session, protocol, version, subject, "Pulse", 70)
        return {"protocol": protocol.id, "bgh": sites["BGH"].id, "mrc": sites["MRC"].id,
                "observation": observation.id, "subject": subject.id, "sponsor": organisation}


def ask(client, protocol_id, text="Hospital question"):
    response = client.post("/api/queries", json={"protocol_id": protocol_id, "text": text})
    assert response.status_code == 200, response.text
    return response.json()


def inbox(client, **filters):
    response = client.get("/api/notifications", params=filters)
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, protocol_id):
    response = client.post(f"/api/studies/{protocol_id}/submission", json={"confirmed": True})
    assert response.status_code == 200, response.text
    return response.json()


def test_notification_and_submission_authentication_and_roles(client, assigned):
    client.post("/api/auth/logout")
    for path in ("/api/notifications", f"/api/studies/{assigned['protocol']}/submission"):
        assert client.get(path).status_code == 401
    assert client.post("/api/notifications/1/read").status_code == 401
    assert client.post("/api/notifications/read-all", json={"through_id": 1}).status_code == 401
    login(client, BGH)
    assert client.get("/api/notifications").status_code == 403
    assert client.post("/api/notifications/1/read").status_code == 403
    assert client.post("/api/notifications/read-all", json={"through_id": 1}).status_code == 403
    login(client, BUILDER)
    assert client.get(f"/api/studies/{assigned['protocol']}/submission").status_code == 403
    assert client.post(f"/api/studies/{assigned['protocol']}/submission", json={"confirmed": True}).status_code == 403


def test_new_hospital_query_creates_one_persistent_alert(client, assigned):
    assert inbox(client) == {"items": [], "unread_count": 0, "next_before_id": None}
    login(client, BGH)
    question = ask(client, assigned["protocol"])
    login(client, BUILDER)
    result = inbox(client)
    assert result["unread_count"] == len(result["items"]) == 1
    item = result["items"][0]
    assert item["kind"] == "hospital_query"
    assert item["query_id"] == question["id"]
    assert item["hospital_name"] == "Boston General Demo"
    assert item["destination"] == f"/sponsor/queries?query={question['id']}"
    assert item["read_at"] is None
    assert item["created_at"].endswith("Z")
    assert inbox(client) == result
    with db.session() as session:
        assert session.scalar(select(func.count(Notification.id))) == 1


def test_sponsor_query_and_saved_data_do_not_create_completion_alerts(client, assigned):
    response = client.post("/api/queries", json={"protocol_id": assigned["protocol"],
                                                "site_org_id": assigned["bgh"], "text": "Sponsor question"})
    assert response.status_code == 200
    assert inbox(client)["items"] == []
    with db.session() as session:
        assert session.scalar(select(func.count(HospitalSubmission.id))) == 0


def test_value_query_shortcut_produces_only_one_alert(client, assigned):
    login(client, BGH)
    response = client.post(f"/api/data/{assigned['observation']}/queries", json={"text": "Please clarify"})
    assert response.status_code == 200
    login(client, BUILDER)
    assert len(inbox(client)["items"]) == 1


def test_query_and_alert_are_committed_atomically(client, assigned, monkeypatch):
    from ecrf.api import queries

    def broken_notification(**values):
        raise RuntimeError("Notification persistence unavailable")

    monkeypatch.setattr(queries, "Notification", broken_notification)
    login(client, BGH)
    with pytest.raises(RuntimeError, match="Notification persistence unavailable"):
        client.post(f"/api/data/{assigned['observation']}/queries", json={"text": "A question"})
    with db.session() as session:
        assert session.scalar(select(func.count(Query.id))) == 0
        assert session.scalar(select(func.count(Notification.id))) == 0
        assert session.get(Observation, assigned["observation"]).status == "entered"


def test_read_receipts_are_personal_persistent_and_idempotent(client, assigned):
    login(client, BGH)
    ask(client, assigned["protocol"])
    login(client, BUILDER)
    notification_id = inbox(client)["items"][0]["id"]
    for _attempt in range(2):
        assert client.post(f"/api/notifications/{notification_id}/read").status_code == 200
    assert inbox(client)["unread_count"] == 0
    assert inbox(client)["items"][0]["read_at"] is not None
    assert inbox(client, unread_only=True)["items"] == []
    login(client, SPONSOR2)
    assert inbox(client)["unread_count"] == 1
    login(client, BUILDER)
    assert inbox(client)["unread_count"] == 0
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(NotificationRead)) == 1


def test_other_sponsor_cannot_list_or_mark_an_alert_read(client, assigned):
    login(client, BGH)
    ask(client, assigned["protocol"])
    login(client, BUILDER)
    notification_id = inbox(client)["items"][0]["id"]
    with db.session() as session:
        organisation = Organisation(name="Other sponsor", code="OTHER", type="sponsor")
        session.add(organisation)
        session.flush()
        session.add(User(org_id=organisation.id, role="sponsor", email="notify@other.demo", name="Other",
                         password_hash=hash_password(PASSWORD), is_active=True))
    login(client, "notify@other.demo")
    assert inbox(client)["items"] == []
    assert inbox(client)["unread_count"] == 0
    assert client.post(f"/api/notifications/{notification_id}/read").status_code == 404
    assert client.post("/api/notifications/read-all", json={"through_id": notification_id}).status_code == 200
    login(client, BUILDER)
    assert inbox(client)["unread_count"] == 1


def test_pagination_and_mark_all_respect_displayed_cutoff(client, assigned):
    login(client, BGH)
    for number in range(3):
        ask(client, assigned["protocol"], f"Question {number}")
    login(client, BUILDER)
    first = inbox(client, limit=2)
    assert len(first["items"]) == 2
    assert first["unread_count"] == 3
    cutoff = first["items"][0]["id"]
    older = inbox(client, before_id=first["next_before_id"], limit=2)
    assert len(older["items"]) == 1
    assert older["next_before_id"] is None
    assert not {item["id"] for item in older["items"]} & {item["id"] for item in first["items"]}
    login(client, BGH)
    ask(client, assigned["protocol"], "New while reading")
    login(client, BUILDER)
    assert client.post("/api/notifications/read-all", json={"through_id": cutoff}).status_code == 200
    assert inbox(client)["unread_count"] == 1
    assert len(inbox(client, unread_only=True)["items"]) == 1
    for filters in ({"limit": 0}, {"limit": 51}, {"before_id": 0}):
        assert client.get("/api/notifications", params=filters).status_code == 422


def test_hospital_explicitly_submits_its_entire_ecrf_once(client, assigned):
    login(client, BGH)
    initial = client.get(f"/api/studies/{assigned['protocol']}/submission").json()
    assert initial["state"] == "not_submitted" and initial["can_submit"] is True
    assert client.post(f"/api/studies/{assigned['protocol']}/submission", json={}).status_code == 422
    result = submit(client, assigned["protocol"])
    assert result["state"] == "submitted"
    assert result["submitted_by"] == BGH
    assert result["patient_count"] == 1
    assert submit(client, assigned["protocol"]) == result
    login(client, BUILDER)
    notifications = inbox(client)
    assert notifications["unread_count"] == len(notifications["items"]) == 1
    item = notifications["items"][0]
    assert item["kind"] == "ecrf_submitted"
    assert item["destination"] == f"/sponsor/ecrf-status?hospital={assigned['bgh']}&protocol={assigned['protocol']}"
    progress = client.get("/api/sponsor/ecrf-status").json()
    hospital = next(row for row in progress["hospitals"] if row["site_id"] == assigned["bgh"])
    assert hospital["protocols"][0]["submission"]["state"] == "submitted"
    with db.session() as session:
        assert session.scalar(select(func.count(HospitalSubmission.id))) == 1
        assert session.get(Observation, assigned["observation"]).status == "entered"


def test_empty_unassigned_and_other_sites_cannot_be_submitted(client, assigned):
    login(client, MRC)
    assert client.post(f"/api/studies/{assigned['protocol']}/submission", json={"confirmed": True, "site_org_id": assigned["bgh"]}).status_code == 409
    login(client, BGH)
    with db.session() as session:
        assignment = session.scalar(select(ProtocolSite).where(ProtocolSite.protocol_id == assigned["protocol"], ProtocolSite.site_org_id == assigned["bgh"]))
        session.delete(assignment)
    assert client.post(f"/api/studies/{assigned['protocol']}/submission", json={"confirmed": True}).status_code == 404
    assert client.get(f"/api/studies/{assigned['protocol']}/submission").status_code == 404
    login(client, BUILDER)
    assert inbox(client)["items"] == []


def test_changes_require_resubmission_but_sponsor_approval_does_not(client, assigned):
    login(client, BGH)
    before = submit(client, assigned["protocol"])
    login(client, BUILDER)
    assert client.post(f"/api/protocols/{assigned['protocol']}/data/approve", json={"observation_ids": [assigned["observation"]]}).status_code == 200
    login(client, BGH)
    assert client.get(f"/api/studies/{assigned['protocol']}/submission").json() == before
    assert client.post(f"/api/studies/{assigned['protocol']}/subjects", json={}).status_code == 200
    changed = client.get(f"/api/studies/{assigned['protocol']}/submission").json()
    assert changed["state"] == "changed"
    after = submit(client, assigned["protocol"])
    assert after["submission_id"] != before["submission_id"]
    assert after["patient_count"] == 2
    login(client, BUILDER)
    assert len(inbox(client)["items"]) == 2


def test_hospital_data_correction_requires_resubmission(client, assigned):
    login(client, BGH)
    before = submit(client, assigned["protocol"])
    assert client.post("/api/data/enter", json={"protocol_id": assigned["protocol"], "subject_id": "BGH-001",
                                               "visit": "Screening", "readings": [{"field_name": "Pulse", "value": 75}]}).status_code == 200
    assert client.get(f"/api/studies/{assigned['protocol']}/submission").json()["state"] == "changed"
    assert submit(client, assigned["protocol"])["submission_id"] != before["submission_id"]


def test_other_hospital_changes_do_not_invalidate_a_submission(client, assigned):
    login(client, BGH)
    before = submit(client, assigned["protocol"])
    login(client, MRC)
    assert client.post(f"/api/studies/{assigned['protocol']}/subjects", json={}).status_code == 200
    login(client, BGH)
    assert client.get(f"/api/studies/{assigned['protocol']}/submission").json() == before


def test_schema_upgrade_preserves_protocols_forms_and_queries(tmp_path):
    configuration = migrate.alembic_config()
    database_url = f"sqlite:///{tmp_path / 'notifications-upgrade.db'}"
    configuration.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(configuration, "0010")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(Organisation.__table__.insert(), [
            {"id": 999, "name": "Sponsor", "type": "sponsor", "code": "SP"},
            {"id": 1000, "name": "Hospital", "type": "site", "code": "HS"},
        ])
        connection.execute(Protocol.__table__.insert(), {"id": 999, "org_id": 999, "name": "Existing",
            "filename": "existing.pdf", "text_hash": "existing", "normalised": "Existing", "sections": [],
            "pages": 1, "tokens_estimate": 1, "uploaded_by": BUILDER})
        connection.execute(ECRFVersion.__table__.insert(), {"protocol_id": 999, "protocol_hash": "existing",
            "version": 1, "content": {"forms": []}, "created_by": BUILDER, "state": "locked"})
        connection.execute(Query.__table__.insert(), {"protocol_id": 999, "site_org_id": 1000,
            "raised_by": BGH, "raised_by_org": "site", "text": "Existing question", "status": "open"})
    command.upgrade(configuration, "head")
    with engine.connect() as connection:
        assert connection.scalar(select(Protocol.name).where(Protocol.id == 999)) == "Existing"
        assert connection.scalar(select(ECRFVersion.state).where(ECRFVersion.protocol_id == 999)) == "locked"
        assert connection.scalar(select(Query.text)) == "Existing question"
        assert connection.scalar(select(func.count(Notification.id))) == 0
    assert {"hospital_submission", "notification", "notification_read"} <= set(inspect(engine).get_table_names())
    engine.dispose()
