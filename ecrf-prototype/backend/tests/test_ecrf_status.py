from datetime import datetime

from conftest import BGH, BUILDER, MRC, PASSWORD, login
from sqlalchemy import select

from ecrf.auth.passwords import hash_password
from ecrf.storage import db
from ecrf.storage.models import (
    ECRFVersion,
    Observation,
    ObservationHistory,
    Organisation,
    Protocol,
    ProtocolSite,
    Query,
    Study,
    StudyProtocol,
    Subject,
    User,
)

URL = "/api/sponsor/ecrf-status"
CREATED = datetime(2026, 1, 1)
UPDATED = datetime(2026, 1, 2)
LATER = datetime(2026, 1, 3)


def field(name, kind="integer", required=True, repeats=1, status="approved"):
    return {"name": name, "type": kind, "required": required, "repeats": repeats,
            "status": status, "source": {"section": "1", "quote": "Synthetic source for test form fields."}}


def add_protocol(session, org_id, name="Test protocol", study=True, locked=True, forms=None):
    protocol = Protocol(org_id=org_id, name=name, filename=f"{name}.pdf", text_hash=name,
                        normalised=name, sections=[], pages=1, tokens_estimate=1,
                        uploaded_by=BUILDER, uploaded_at=CREATED)
    session.add(protocol)
    session.flush()
    if study:
        grouping = Study(org_id=org_id, code=name.upper(), name=f"{name} study", created_by=BUILDER)
        session.add(grouping)
        session.flush()
        session.add(StudyProtocol(protocol_id=protocol.id, study_id=grouping.id, assigned_by=BUILDER))
    version = ECRFVersion(protocol_id=protocol.id, protocol_hash=name, version=1,
                          state="locked" if locked else "draft", created_by=BUILDER,
                          content={"protocol_id": protocol.id, "protocol_hash": name,
                                   "backend": "mock", "model": "mock", "forms": forms if forms is not None else [
                                       {"visit": "Screening", "fields": [field("Pulse", repeats=2), field("Consent", "boolean")]},
                                       {"visit": "Week 4", "fields": [field("Weight", "decimal")]},
                                       {"visit": "Week 12", "fields": [field("Note", "text", False)]},
                                       {"visit": "Rejected only", "fields": [field("Unused", status="rejected")]},
                                   ]})
    session.add(version)
    session.flush()
    return protocol, version


def add_subject(session, protocol, site, code):
    subject = Subject(protocol_id=protocol.id, site_org_id=site.id, code=code,
                      created_by=BGH if site.code == "BGH" else MRC, created_at=CREATED)
    session.add(subject)
    session.flush()
    return subject


def reading(session, protocol, version, subject, name, value, repeat=1, visit="Screening"):
    observation = Observation(protocol_id=protocol.id, ecrf_version_id=version.id if version else None,
                              subject_ref=subject.id, subject_id=subject.code, visit=visit,
                              field_name=name, repeat_num=repeat, status="entered", entered_by=subject.created_by,
                              value_num=value if isinstance(value, (int, float)) else None,
                              value_text=value if isinstance(value, str) else None, entered_at=CREATED)
    session.add(observation)
    session.flush()
    return observation


def first_protocol(client):
    response = client.get(URL)
    assert response.status_code == 200, response.text
    return response.json()["hospitals"][0]["protocols"][0]


def test_requires_sponsor_session(client, demo_accounts):
    assert client.get(URL).status_code == 401
    login(client, BGH)
    assert client.get(URL).status_code == 403


def test_empty_tracker_has_no_invented_activity(client, demo_accounts):
    login(client, BUILDER)
    assert client.get(URL).json() == {"hospitals": [], "studies": [], "protocols": []}


def test_groups_multiple_protocols_once_per_hospital_including_empty_assignments(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        sites = session.scalars(select(Organisation).where(Organisation.type == "site").order_by(Organisation.code)).all()
        for name, locked in (("Locked", True), ("Draft", False)):
            protocol, _ = add_protocol(session, organisation, name, study=False, locked=locked)
            for site in sites:
                session.add(ProtocolSite(protocol_id=protocol.id, site_org_id=site.id, assigned_by=BUILDER))
    result = client.get(URL).json()
    assert len(result["hospitals"]) == 2
    assert [hospital["site_code"] for hospital in result["hospitals"]] == ["BGH", "MRC"]
    for hospital in result["hospitals"]:
        assert [form["protocol_name"] for form in hospital["protocols"]] == ["Draft", "Locked"]
        for form in hospital["protocols"]:
            assert form["assigned"] is True
            assert form["patient_count"] == form["patients_with_entries"] == 0
            assert form["last_hospital_update"] is None
            assert form["study_id"] is None
            assert form["patients"] == []
        assert [form["locked_version"] for form in hospital["protocols"]] == [None, 1]


def test_saved_entries_and_visits_without_entries_have_no_completion_rules(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        site = session.scalar(select(Organisation).where(Organisation.code == "BGH"))
        protocol, version = add_protocol(session, organisation)
        subject = add_subject(session, protocol, site, "BGH-001")
        add_subject(session, protocol, site, "BGH-002")
        reading(session, protocol, version, subject, "Pulse", 0)
        reading(session, protocol, version, subject, "Consent", "No")
        reading(session, protocol, version, subject, "Pulse", None, repeat=2)
        reading(session, protocol, version, subject, "Note", "  ", visit="Week 12")
    form = first_protocol(client)
    assert form["study_name"] == "Test protocol study"
    assert (form["patient_count"], form["patients_with_entries"]) == (2, 1)
    patient = form["patients"][0]
    assert patient["latest_visits"] == ["Screening", "Week 12"]
    assert patient["last_hospital_update"] == "2026-01-01T00:00:00Z"
    assert [(visit["visit"], visit["has_entries"]) for visit in patient["visits"]] == [
        ("Screening", True), ("Week 4", False), ("Week 12", False)]
    assert all(not visit["has_entries"] for visit in form["patients"][1]["visits"])
    for forbidden in ("filled_forms", "scheduled_forms", "approved_values", "unresolved_queries", "overdue", "completion_basis"):
        assert forbidden not in str(form)


def test_latest_visit_is_latest_hospital_edit_not_furthest_week(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        site = session.scalar(select(Organisation).where(Organisation.code == "BGH"))
        protocol, version = add_protocol(session, organisation)
        subject = add_subject(session, protocol, site, "BGH-001")
        earlier = reading(session, protocol, version, subject, "Pulse", 70)
        reading(session, protocol, version, subject, "Weight", 80, visit="Week 4").entered_at = UPDATED
        earlier.updated_at = LATER
        session.add(ObservationHistory(observation_id=earlier.id, old_value="69", new_value="70",
                                       changed_by=BGH, changed_at=LATER))
    patient = first_protocol(client)["patients"][0]
    assert patient["latest_visits"] == ["Screening"]
    assert patient["last_hospital_update"] == "2026-01-03T00:00:00Z"
    visits = {visit["visit"]: visit for visit in patient["visits"]}
    assert visits["Week 4"]["last_hospital_update"] == "2026-01-02T00:00:00Z"


def test_sponsor_approvals_queries_and_assignment_do_not_advance_hospital_activity(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        site = session.scalar(select(Organisation).where(Organisation.code == "BGH"))
        protocol, version = add_protocol(session, organisation)
        subject = add_subject(session, protocol, site, "BGH-001")
        observation = reading(session, protocol, version, subject, "Pulse", 70)
        observation.status, observation.approved_by, observation.approved_at = "approved", BUILDER, LATER
        observation.updated_at = LATER
        session.add(ObservationHistory(observation_id=observation.id, old_value="69", new_value="70",
                                       changed_by=BUILDER, changed_at=LATER))
        session.add(ProtocolSite(protocol_id=protocol.id, site_org_id=site.id, assigned_by=BUILDER, assigned_at=LATER))
        session.add(Query(protocol_id=protocol.id, site_org_id=site.id, subject_ref=subject.id,
                          raised_by=BUILDER, raised_at=LATER, text="Synthetic question",
                          status="closed", closed_by=BUILDER, closed_at=LATER))
    form = first_protocol(client)
    assert form["last_hospital_update"] == "2026-01-01T00:00:00Z"
    assert form["patients"][0]["latest_visits"] == ["Screening"]


def test_hospitals_and_sponsors_are_isolated_and_unassignment_keeps_site_updates(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        bgh = session.scalar(select(Organisation).where(Organisation.code == "BGH"))
        mrc = session.scalar(select(Organisation).where(Organisation.code == "MRC"))
        protocol, version = add_protocol(session, organisation)
        bgh_subject = add_subject(session, protocol, bgh, "BGH-001")
        add_subject(session, protocol, mrc, "MRC-001")
        session.add(ProtocolSite(protocol_id=protocol.id, site_org_id=mrc.id, assigned_by=BUILDER))
        reading(session, protocol, version, bgh_subject, "Pulse", 0)
        other = Organisation(name="Private sponsor", code="PRIVATE", type="sponsor")
        session.add(other)
        session.flush()
        session.add(User(email="tracker@other.demo", name="Other", org_id=other.id, role="sponsor",
                         password_hash=hash_password(PASSWORD), is_active=True))
        private, private_version = add_protocol(session, other.id, "Secret")
        private_subject = add_subject(session, private, bgh, "BGH-SECRET")
        reading(session, private, private_version, private_subject, "Consent", "Yes")
    result = client.get(URL).json()
    assert {item["name"] for item in result["protocols"]} == {"Test protocol"}
    rows = {row["site_code"]: row["protocols"][0] for row in result["hospitals"]}
    assert rows["BGH"]["patients_with_entries"] == 1
    assert rows["BGH"]["assigned"] is False
    assert rows["MRC"]["patients_with_entries"] == 0
    assert rows["MRC"]["assigned"] is True
    assert rows["MRC"]["patients"][0]["latest_visits"] == []
    assert "BGH-SECRET" not in str(result)
    login(client, "tracker@other.demo")
    private = first_protocol(client)
    assert private["protocol_name"] == "Secret"
    assert private["patients"][0]["subject_code"] == "BGH-SECRET"


def test_unlinked_mismatched_and_previous_version_readings_are_not_hospital_updates(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        site = session.scalar(select(Organisation).where(Organisation.code == "BGH"))
        protocol, version = add_protocol(session, organisation)
        subject = add_subject(session, protocol, site, "BGH-001")
        reading(session, protocol, None, subject, "Pulse", 70)
        reading(session, protocol, version, subject, "Pulse", 71, repeat=2).subject_id = "WRONG"
        reading(session, protocol, version, subject, "Consent", "Yes").subject_ref = None
        reading(session, protocol, version, subject, "Weight", 70, visit="Week 4")
        reading(session, protocol, version, subject, "Unknown", 1).entered_at = LATER
        version2 = ECRFVersion(protocol_id=protocol.id, protocol_hash=protocol.text_hash, version=2,
                               state="locked", created_by=BUILDER, content=version.content)
        session.add(version2)
    form = first_protocol(client)
    assert form["locked_version"] == 2
    assert form["patients_with_entries"] == 0
    assert form["patients"][0]["latest_visits"] == []
    with db.session() as session:
        latest = session.scalar(select(ECRFVersion).where(ECRFVersion.version == 2))
        latest.state = "draft"
    assert first_protocol(client)["patients"][0]["visits"] == []


def test_seeded_records_are_not_presented_as_hospital_updates(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        site = session.scalar(select(Organisation).where(Organisation.code == "BGH"))
        protocol, version = add_protocol(session, organisation)
        session.add(ProtocolSite(protocol_id=protocol.id, site_org_id=site.id, assigned_by=BUILDER))
        subject = add_subject(session, protocol, site, "BGH-SEED")
        subject.created_by = "seed"
        reading(session, protocol, version, subject, "Pulse", 70).entered_by = "seed"
    form = first_protocol(client)
    assert form["patient_count"] == form["patients_with_entries"] == 0
    assert form["last_hospital_update"] is None


def test_real_entry_approval_and_site_query_correction_flow(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        site = session.scalar(select(Organisation).where(Organisation.code == "BGH"))
        protocol, _ = add_protocol(session, organisation)
        protocol_id = protocol.id
        session.add(ProtocolSite(protocol_id=protocol_id, site_org_id=site.id, assigned_by=BUILDER))
    login(client, BGH)
    created = client.post(f"/api/studies/{protocol_id}/subjects", json={})
    assert created.status_code == 200
    entry = {"protocol_id": protocol_id, "subject_id": created.json()["code"], "visit": "Screening", "readings": [
        {"field_name": "Pulse", "repeat_num": 1, "value": 0},
        {"field_name": "Pulse", "repeat_num": 2, "value": 70},
        {"field_name": "Consent", "value": False},
    ]}
    assert client.post("/api/data/enter", json=entry).status_code == 200
    login(client, BUILDER)
    before = first_protocol(client)
    assert (before["patient_count"], before["patients_with_entries"]) == (1, 1)
    data = client.get(f"/api/protocols/{protocol_id}/data").json()
    observation_id = next(row["id"] for row in data if row["field"] == "Pulse" and row["repeat"] == 1)
    assert client.post(f"/api/protocols/{protocol_id}/data/approve", json={"observation_ids": [row["id"] for row in data]}).status_code == 200
    assert first_protocol(client) == before
    question = client.post(f"/api/data/{observation_id}/queries", json={"text": "Please verify this value"})
    assert question.status_code == 200
    assert first_protocol(client) == before
    login(client, BGH)
    corrected = client.post(f"/api/queries/{question.json()['id']}/answer",
                            json={"text": "Corrected", "new_value": "1"})
    assert corrected.status_code == 200
    login(client, BUILDER)
    after = first_protocol(client)
    assert after["patients"][0]["latest_visits"] == ["Screening"]
    assert after["last_hospital_update"] > before["last_hospital_update"]
    login(client, MRC)
    assert client.get(URL).status_code == 403


def test_cleared_visit_is_a_hospital_update_but_has_no_saved_entries(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        site = session.scalar(select(Organisation).where(Organisation.code == "BGH"))
        protocol, version = add_protocol(session, organisation)
        subject = add_subject(session, protocol, site, "BGH-001")
        observation = reading(session, protocol, version, subject, "Note", None, visit="Week 12")
        observation.updated_at = UPDATED
        session.add(ObservationHistory(observation_id=observation.id, old_value="note", new_value=None,
                                       changed_by=BGH, changed_at=UPDATED))
    form = first_protocol(client)
    patient = form["patients"][0]
    assert patient["latest_visits"] == ["Week 12"]
    assert form["patients_with_entries"] == 0
    assert patient["visits"][-1]["has_entries"] is False
    assert patient["last_hospital_update"] == "2026-01-02T00:00:00Z"


def test_only_the_patients_own_hospital_can_supply_an_update(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        site = session.scalar(select(Organisation).where(Organisation.code == "BGH"))
        protocol, version = add_protocol(session, organisation)
        session.add(ProtocolSite(protocol_id=protocol.id, site_org_id=site.id, assigned_by=BUILDER))
        subject = add_subject(session, protocol, site, "BGH-001")
        subject.created_by = BUILDER
        observation = reading(session, protocol, version, subject, "Pulse", 70)
        observation.entered_by = MRC
        observation_id = observation.id
        session.add(ObservationHistory(observation_id=observation.id, old_value="69", new_value="70",
                                       changed_by=MRC, changed_at=UPDATED))
    assert first_protocol(client)["patient_count"] == 0
    with db.session() as session:
        session.add(ObservationHistory(observation_id=observation_id, old_value="69", new_value="70",
                                       changed_by=BGH, changed_at=LATER))
    form = first_protocol(client)
    assert form["patient_count"] == form["patients_with_entries"] == 1
    assert form["patients"][0]["registered_at"] is None
    assert form["last_hospital_update"] == "2026-01-03T00:00:00Z"


def test_latest_hospital_date_compares_timestamps_not_iso_strings(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        site = session.scalar(select(Organisation).where(Organisation.code == "BGH"))
        protocol, _ = add_protocol(session, organisation)
        first = add_subject(session, protocol, site, "BGH-001")
        second = add_subject(session, protocol, site, "BGH-002")
        first.created_at = UPDATED
        second.created_at = UPDATED.replace(microsecond=100)
    assert first_protocol(client)["last_hospital_update"] == "2026-01-02T00:00:00.000100Z"
