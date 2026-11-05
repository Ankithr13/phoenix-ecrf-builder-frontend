from pathlib import Path

import pytest
from alembic import command
from conftest import BGH, BUILDER, PASSWORD, login
from sqlalchemy import create_engine, select

from ecrf import ingest
from ecrf.auth.passwords import hash_password
from ecrf.config import config
from ecrf.storage import db, migrate
from ecrf.storage.models import ECRFVersion, Organisation, Protocol, User


def create_study(client, code="PHX-401", name="Phoenix Research"):
    response = client.post("/api/sponsor/studies", json={"code": code, "name": name})
    assert response.status_code == 201, response.text
    return response.json()


def test_study_identifiers_are_normalised_and_unique_per_sponsor(client, demo_accounts):
    login(client, BUILDER)
    study = create_study(client, " phx-401 ", "  Phoenix   Research  ")
    assert (study["code"], study["name"], study["protocol_count"]) == (
        "PHX-401", "Phoenix Research", 0)
    assert client.post("/api/sponsor/studies", json={
        "code": "PHX-401", "name": "Another name"}).status_code == 409
    assert client.get(f"/api/sponsor/studies/{study['id']}").json() == study
    assert len(client.get("/api/sponsor/studies").json()) == 1


@pytest.mark.parametrize("body", [
    {"code": "", "name": "Study"}, {"code": "A", "name": "   "},
    {"code": "A B", "name": "Study"}, {"code": "A", "name": "N" * 201},
])
def test_study_input_validation(client, demo_accounts, body):
    login(client, BUILDER)
    assert client.post("/api/sponsor/studies", json=body).status_code == 422


def test_existing_protocols_remain_unassigned_until_selected(client, demo_accounts):
    login(client, BUILDER)
    protocol_id = client.post("/api/protocols/sample").json()["id"]
    before = client.get("/api/protocols").json()[0]
    assert before["study_id"] is None
    study = create_study(client)
    response = client.put(f"/api/protocols/{protocol_id}/study", json={"study_id": study["id"]})
    assert response.status_code == 200
    assigned = client.get("/api/protocols", params={"study_id": study["id"]}).json()
    assert [protocol["id"] for protocol in assigned] == [protocol_id]
    assert assigned[0]["study_name"] == study["name"]
    assert assigned[0]["study_code"] == study["code"]
    for field in ("name", "pages", "latest_version", "state", "summary"):
        assert assigned[0][field] == before[field]
    assert client.get("/api/protocols?unassigned=true").json() == []
    assert client.get("/api/sponsor/studies").json()[0]["protocol_count"] == 1
    assert client.put(f"/api/protocols/{protocol_id}/study", json={"study_id": None}).status_code == 200
    assert client.get("/api/protocols?unassigned=true").json()[0]["id"] == protocol_id


def test_multiple_protocols_and_explicit_reassignment(client, demo_accounts, monkeypatch):
    login(client, BUILDER)
    first_study = create_study(client)
    second_study = create_study(client, "PHX-402", "Second study")
    stored_paths = []

    def parse_upload(path):
        stored_paths.append(Path(path))
        text = Path(path).read_text()
        return ingest.Document(text=text, pages=1, hash=text, tokens_estimate=5)

    monkeypatch.setattr(ingest, "load", parse_upload)
    protocol_ids = []
    for text in ("Original protocol", "Protocol amendment"):
        response = client.post("/api/protocols/upload", data={"study_id": first_study["id"]},
                               files={"file": ("protocol.pdf", text.encode(), "application/pdf")})
        assert response.status_code == 200, response.text
        protocol_ids.append(response.json()["id"])
    assert len(set(protocol_ids)) == 2
    assert [path.read_text() for path in stored_paths] == ["Original protocol", "Protocol amendment"]
    assert client.get(f"/api/sponsor/studies/{first_study['id']}").json()["protocol_count"] == 2
    assert client.put(f"/api/protocols/{protocol_ids[1]}/study", json={
        "study_id": second_study["id"]}).status_code == 200
    assert client.get(f"/api/sponsor/studies/{first_study['id']}").json()["protocol_count"] == 1
    assert client.get(f"/api/sponsor/studies/{second_study['id']}").json()["protocol_count"] == 1


def test_duplicate_upload_cannot_silently_move_between_studies(client, demo_accounts):
    login(client, BUILDER)
    first_study = create_study(client)
    second_study = create_study(client, "PHX-402", "Second study")
    protocol_id = client.post("/api/protocols/sample", params={"study_id": first_study["id"]}).json()["id"]
    repeated = client.post("/api/protocols/sample", params={"study_id": first_study["id"]})
    assert repeated.json()["already_loaded"] is True
    assert repeated.json()["id"] == protocol_id
    source = config.data_dir / "sample" / "PHX-401-201_protocol.pdf"
    with source.open("rb") as document:
        response = client.post("/api/protocols/upload", data={"study_id": second_study["id"]},
                               files={"file": (source.name, document, "application/pdf")})
    assert response.status_code == 409
    assert client.post("/api/protocols/sample", params={"study_id": second_study["id"]}).status_code == 409
    assert client.get("/api/protocols").json()[0]["study_id"] == first_study["id"]
    assert client.get(f"/api/sponsor/studies/{second_study['id']}").json()["protocol_count"] == 0


def test_an_unassigned_duplicate_can_be_assigned_during_upload(client, demo_accounts):
    login(client, BUILDER)
    protocol_id = client.post("/api/protocols/sample").json()["id"]
    study = create_study(client)
    source = config.data_dir / "sample" / "PHX-401-201_protocol.pdf"
    with source.open("rb") as document:
        response = client.post("/api/protocols/upload", data={"study_id": study["id"]},
                               files={"file": (source.name, document, "application/pdf")})
    assert response.status_code == 200, response.text
    assert response.json()["id"] == protocol_id
    assert response.json()["already_loaded"] is True
    assert client.get("/api/protocols").json()[0]["study_id"] == study["id"]


def test_study_management_requires_a_sponsor_and_a_session(client, demo_accounts):
    assert client.get("/api/sponsor/studies").status_code == 401
    login(client, BGH)
    assert client.get("/api/sponsor/studies").status_code == 403
    assert client.post("/api/sponsor/studies", json={"code": "A", "name": "Study"}).status_code == 403
    assert client.get("/api/sponsor/studies/1").status_code == 403
    assert client.put("/api/protocols/1/study", json={"study_id": 1}).status_code == 403


def test_loading_sample_after_upload_reuses_the_same_document(client, demo_accounts):
    login(client, BUILDER)
    study = create_study(client)
    source = config.data_dir / "sample" / "PHX-401-201_protocol.pdf"
    with source.open("rb") as document:
        uploaded = client.post("/api/protocols/upload", data={"study_id": study["id"]},
                               files={"file": ("renamed.pdf", document, "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    sample = client.post("/api/protocols/sample", params={"study_id": study["id"]})
    assert sample.status_code == 200
    assert sample.json()["already_loaded"] is True
    assert sample.json()["id"] == uploaded.json()["id"]
    assert len(client.get("/api/protocols").json()) == 1


def test_study_and_protocol_assignment_are_scoped_to_the_sponsor(client, demo_accounts):
    login(client, BUILDER)
    study = create_study(client)
    protocol_id = client.post("/api/protocols/sample").json()["id"]
    with db.session() as session:
        other = Organisation(name="Other Sponsor", type="sponsor", code="OTH")
        session.add(other)
        session.flush()
        session.add(User(email="study@other.demo", name="Other Sponsor", org_id=other.id,
                         role="sponsor", password_hash=hash_password(PASSWORD), is_active=True))
    login(client, "study@other.demo")
    assert client.get("/api/sponsor/studies").json() == []
    assert client.get(f"/api/sponsor/studies/{study['id']}").status_code == 404
    assert client.get("/api/protocols", params={"study_id": study["id"]}).status_code == 404
    assert client.put(f"/api/protocols/{protocol_id}/study", json={"study_id": None}).status_code == 404
    own_protocol = client.post("/api/protocols/sample").json()["id"]
    assert client.put(f"/api/protocols/{own_protocol}/study", json={"study_id": study["id"]}).status_code == 404
    assert client.post("/api/protocols/sample", params={"study_id": study["id"]}).status_code == 404
    with (config.data_dir / "sample" / "PHX-401-201_protocol.pdf").open("rb") as document:
        assert client.post("/api/protocols/upload", data={"study_id": study["id"]},
                           files={"file": ("protocol.pdf", document, "application/pdf")}).status_code == 404
    assert create_study(client)["code"] == study["code"]


def test_assignment_does_not_change_existing_ecrf_versions(client, demo_accounts):
    login(client, BUILDER)
    protocol_id = client.post("/api/protocols/sample").json()["id"]
    assert client.post(f"/api/protocols/{protocol_id}/extract").status_code == 200
    before = client.get(f"/api/protocols/{protocol_id}/draft").json()
    study = create_study(client)
    assert client.put(f"/api/protocols/{protocol_id}/study", json={"study_id": study["id"]}).status_code == 200
    assert client.get(f"/api/protocols/{protocol_id}/draft").json() == before


def test_migration_preserves_existing_protocols_and_versions(tmp_path):
    migration_config = migrate.alembic_config()
    database_url = f"sqlite:///{tmp_path / 'previous.db'}"
    migration_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(migration_config, "0009")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(Organisation.__table__.insert(), {
            "id": 999, "name": "Sponsor", "type": "sponsor", "code": "SP"})
        connection.execute(Protocol.__table__.insert(), {
            "id": 999, "org_id": 999, "name": "Existing protocol", "filename": "existing.pdf",
            "text_hash": "existing", "normalised": "Existing protocol", "sections": [],
            "pages": 1, "tokens_estimate": 2, "uploaded_by": "sponsor@example.demo"})
        connection.execute(ECRFVersion.__table__.insert(), {
            "protocol_id": 999, "protocol_hash": "existing", "version": 1,
            "content": {"forms": []}, "created_by": "sponsor@example.demo", "state": "locked"})
    command.upgrade(migration_config, "head")
    with engine.connect() as connection:
        assert connection.scalar(select(Protocol.name).where(Protocol.id == 999)) == "Existing protocol"
        assert connection.scalar(select(ECRFVersion.state).where(ECRFVersion.protocol_id == 999)) == "locked"
    engine.dispose()
