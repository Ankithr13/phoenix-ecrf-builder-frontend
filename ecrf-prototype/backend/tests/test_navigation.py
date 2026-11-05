from conftest import BGH, BUILDER, MRC, PASSWORD, login
from sqlalchemy import func, select
from test_ecrf_status import add_protocol, add_subject

from ecrf.auth.passwords import hash_password
from ecrf.storage import db
from ecrf.storage.models import ECRFVersion, Organisation, ProtocolSite, Study, StudyProtocol, User


def context_url(protocol_id):
    return f"/api/navigation/protocols/{protocol_id}"


def test_navigation_context_requires_a_session(client, demo_accounts):
    assert client.get(context_url(1)).status_code == 401


def test_sponsor_context_names_real_study_and_protocol_without_changing_forms(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        protocol, version = add_protocol(session, organisation)
        protocol_id = protocol.id
        before = version.content
    response = client.get(context_url(protocol_id))
    assert response.status_code == 200
    data = response.json()
    assert data["protocol"] == {"id": protocol_id, "name": "Test protocol", "state": "locked"}
    assert data["study"]["name"] == "Test protocol study"
    assert data["study"]["code"] == "TEST PROTOCOL"
    assert data["subject"] is None
    with db.session() as session:
        assert session.scalar(select(func.count(ECRFVersion.id))) == 1
        assert session.scalar(select(ECRFVersion.content)) == before


def test_unassigned_protocol_has_no_invented_study_and_handles_unextracted_forms(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        protocol, version = add_protocol(session, organisation, study=False, locked=False)
        protocol_id = protocol.id
        session.delete(version)
    data = client.get(context_url(protocol_id)).json()
    assert data["study"] is None
    assert data["protocol"]["state"] is None
    assert data["protocol"]["name"] == "Test protocol"


def test_site_context_requires_assignment_and_lock_and_only_returns_its_patient_code(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        sites = {site.code: site for site in session.scalars(select(Organisation).where(Organisation.type == "site"))}
        protocol, _ = add_protocol(session, organisation)
        protocol_id = protocol.id
        own = add_subject(session, protocol, sites["BGH"], "BGH-001")
        own.initials, own.birth_year = "AB", 1980
        add_subject(session, protocol, sites["MRC"], "MRC-001")
        session.add(ProtocolSite(protocol_id=protocol_id, site_org_id=sites["BGH"].id, assigned_by=BUILDER))
        draft, _ = add_protocol(session, organisation, "Draft", locked=False)
        draft_id = draft.id
        session.add(ProtocolSite(protocol_id=draft.id, site_org_id=sites["BGH"].id, assigned_by=BUILDER))
    login(client, BGH)
    data = client.get(context_url(protocol_id), params={"subject": "BGH-001"}).json()
    assert data["subject"] == {"code": "BGH-001"}
    assert data["study"]["name"] == "Test protocol study"
    assert "initials" not in str(data) and "birth_year" not in str(data)
    assert client.get(context_url(protocol_id), params={"subject": "MRC-001"}).status_code == 404
    assert client.get(context_url(protocol_id), params={"subject": "UNKNOWN"}).status_code == 404
    assert client.get(context_url(draft_id)).status_code == 404
    login(client, MRC)
    assert client.get(context_url(protocol_id)).status_code == 404


def test_context_is_not_visible_to_another_sponsor(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        protocol, _ = add_protocol(session, organisation)
        protocol_id = protocol.id
        other = Organisation(name="Other sponsor", type="sponsor", code="OTHER")
        session.add(other)
        session.flush()
        session.add(User(org_id=other.id, role="sponsor", email="navigation@other.demo", name="Other",
                         password_hash=hash_password(PASSWORD), is_active=True))
    login(client, "navigation@other.demo")
    assert client.get(context_url(protocol_id)).status_code == 404
    assert client.get(context_url(999999)).status_code == 404


def test_context_reflects_reassignment_and_unassignment(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        protocol, _ = add_protocol(session, organisation)
        protocol_id = protocol.id
    study = client.post("/api/sponsor/studies", json={"name": "New grouping", "code": "GROUP-2"}).json()
    assert client.put(f"/api/protocols/{protocol_id}/study", json={"study_id": study["id"]}).status_code == 200
    assert client.get(context_url(protocol_id)).json()["study"] == {"id": study["id"], "name": "New grouping", "code": "GROUP-2"}
    assert client.put(f"/api/protocols/{protocol_id}/study", json={"study_id": None}).status_code == 200
    assert client.get(context_url(protocol_id)).json()["study"] is None


def test_inconsistent_imported_study_assignment_does_not_leak_another_sponsors_name(client, demo_accounts):
    organisation = login(client, BUILDER)["org"]["id"]
    with db.session() as session:
        protocol, _ = add_protocol(session, organisation, study=False)
        protocol_id = protocol.id
        other = Organisation(name="Other sponsor", type="sponsor", code="OTHER")
        session.add(other)
        session.flush()
        private = Study(org_id=other.id, name="Private study", code="PRIVATE", created_by=BUILDER)
        session.add(private)
        session.flush()
        session.add(StudyProtocol(protocol_id=protocol_id, study_id=private.id, assigned_by=BUILDER))
    data = client.get(context_url(protocol_id)).json()
    assert data["study"] is None
    assert "Private study" not in str(data)
