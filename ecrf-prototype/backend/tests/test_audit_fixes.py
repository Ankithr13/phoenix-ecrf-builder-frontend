"""Sprint 3, stage 1: the bugs the November audit found."""

import os
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import APPROVER, BGH, BUILDER, login
from sqlalchemy import inspect, select
from test_cost import _run, fake_llm  # noqa: F401
from test_lock_sites_data import _org_id, entry, lock_and_assign, site_client, sponsor_draft

import ecrf.extract.base as base_mod
from ecrf.api import dashboard as dash_mod
from ecrf.api import protocols as protocols_mod
from ecrf.config import DEV_SECRET_KEY, check_production, config, docs_settings
from ecrf.storage import db
from ecrf.storage.models import LLMCall, Observation

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parent / "data" / "sample" / "PHX-401-201_protocol.pdf"
ROOT = HERE.parents[2] / "test_protocols"


def _upload(c, name: str, path: Path):
    with path.open("rb") as f:
        return c.post("/api/protocols/upload", files={"file": (name, f, "application/pdf")})


def _entered():
    pid = sponsor_draft()
    sponsor = lock_and_assign(pid, "BGH", "MRC")
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects")
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130)).status_code == 200
    return pid, sponsor, bgh, sponsor.get(f"/api/protocols/{pid}/data").json()[0]


def test_upload_filename_cannot_escape_upload_folder(client, demo_accounts):
    login(client, BUILDER)
    upload_dir = protocols_mod.UPLOAD_DIR
    outside = upload_dir.parent / "escaped.pdf"
    r = _upload(client, "../escaped.pdf", SAMPLE)
    assert r.status_code == 200 and not outside.exists()
    p = next(x for x in client.get("/api/protocols").json() if x["id"] == r.json()["id"])
    assert p["filename"] == "escaped.pdf", "only the base name is kept"
    assert _upload(client, "..\\..\\notes.txt", SAMPLE).status_code == 400
    assert _upload(client, "folder/.pdf", SAMPLE).status_code == 400
    stored = [n for n in os.listdir(upload_dir) if n.endswith(".pdf")]
    assert stored and all(len(n) == 36 for n in stored), "32 hex characters plus .pdf"


def test_upload_with_same_name_does_not_replace_stored_pdf(client, demo_accounts):
    login(client, BUILDER)
    before = set(os.listdir(protocols_mod.UPLOAD_DIR))
    assert _upload(client, "same.pdf", SAMPLE).status_code == 200
    first = set(os.listdir(protocols_mod.UPLOAD_DIR)) - before
    assert len(first) == 1
    kept = protocols_mod.UPLOAD_DIR / first.pop()
    original = kept.read_bytes()
    assert _upload(client, "same.pdf", ROOT / "test_protocol2.pdf").status_code == 200
    assert kept.read_bytes() == original
    # A duplicate leaves nothing behind.
    count = len(os.listdir(protocols_mod.UPLOAD_DIR))
    assert _upload(client, "same.pdf", SAMPLE).json()["already_loaded"] is True
    assert len(os.listdir(protocols_mod.UPLOAD_DIR)) == count


def test_site_cannot_close_a_query(client, demo_accounts):
    _, sponsor, bgh, row = _entered()
    q = bgh.post(f"/api/data/{row['id']}/queries", json={"text": "which unit?"}).json()
    assert bgh.post(f"/api/queries/{q['id']}/close").status_code == 403
    assert sponsor.post(f"/api/queries/{q['id']}/close").json()["status"] == "closed"


def test_approved_value_edit_needs_open_sponsor_query(client, demo_accounts):
    pid, sponsor, bgh, row = _entered()
    sponsor.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]})
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 135)).status_code == 409

    # A site's own question changes nothing about the approval.
    q = bgh.post(f"/api/data/{row['id']}/queries", json={"text": "can I change this?"}).json()
    assert q["observation_status"] == "approved"
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 135)).status_code == 409
    sponsor.post(f"/api/queries/{q['id']}/close")
    assert sponsor.get(f"/api/protocols/{pid}/data").json()[0]["status"] == "approved"

    # A sponsor's query reopens it; the edit goes back to submitted, with history.
    sponsor.post(f"/api/data/{row['id']}/queries", json={"text": "please re-check"})
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 135)).status_code == 200
    now = sponsor.get(f"/api/protocols/{pid}/data").json()[0]
    assert now["status"] == "submitted" and now["approved_by"] is None and now["value"] == "135"
    hist = sponsor.get(f"/api/protocols/{pid}/data/{row['id']}/history").json()
    assert [(h["old_value"], h["new_value"]) for h in hist] == [("130", "135")]
    # Still not approvable while that query is live.
    assert sponsor.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]}).status_code == 409


def test_query_correction_uses_entry_validation(client, demo_accounts):
    pid = sponsor_draft()
    sponsor = lock_and_assign(pid, "BGH")
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects", json={"birth_year": 1970, "sex": "Male"})
    form = next(f for f in bgh.get(f"/api/protocols/{pid}/draft").json()["draft"]["forms"] if f["visit"] == "Screening")
    fields = {f["name"]: f for f in form["fields"]}
    assert "Weight" in fields and "Height" in fields and "BMI" not in fields
    assert "ECG Performed" in fields and fields["ECG Performed"]["type"] == "boolean"

    def post(field, value, visit="Screening"):
        return bgh.post("/api/data/enter", json=entry(pid, "BGH-001", value, visit=visit, field=field))

    assert post("ECG Performed", "yes").status_code == 200
    assert post("Weight", 80).status_code == 200
    rows = {r["field"]: r for r in sponsor.get(f"/api/protocols/{pid}/data").json()}

    # Yes/no is spelt the same whichever way it arrives.
    q = sponsor.post(f"/api/data/{rows['ECG Performed']['id']}/queries", json={"text": "check"}).json()
    r = bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "was no", "new_value": "false"})
    assert r.status_code == 200 and r.json()["value"] == "No"
    q = sponsor.post(f"/api/data/{rows['Weight']['id']}/queries", json={"text": "check"}).json()
    assert bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "x", "new_value": 99999}).status_code == 422


def test_query_correction_recomputes_derived_value(client, demo_accounts):
    """A form with weight, height and BMI: correcting the weight moves the BMI."""
    pid = sponsor_draft()
    login(client, BUILDER)
    # The sample has no BMI field, so the reviewer makes one out of another.
    r = client.post(f"/api/protocols/{pid}/review", json={"changes": [
        {"visit": "Screening", "name": "Position", "new_name": "BMI", "type": "decimal", "status": "approved"}]})
    assert r.status_code == 200
    sponsor = lock_and_assign(pid, "BGH")
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects")

    def post(field, value):
        return bgh.post("/api/data/enter", json=entry(pid, "BGH-001", value, visit="Screening", field=field))

    assert post("Height", 180).status_code == 200
    assert post("Weight", 80).status_code == 200
    rows = {r["field"]: r for r in sponsor.get(f"/api/protocols/{pid}/data").json()}
    assert rows["BMI"]["value"] == "24.7", "filled in once both inputs are on file"

    q = sponsor.post(f"/api/data/{rows['Weight']['id']}/queries", json={"text": "check the scale"}).json()
    assert bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "was 90", "new_value": 90}).status_code == 200
    rows = {r["field"]: r for r in sponsor.get(f"/api/protocols/{pid}/data").json()}
    assert rows["Weight"]["value"] == "90" and rows["BMI"]["value"] == "27.8"
    hist = sponsor.get(f"/api/protocols/{pid}/data/{rows['BMI']['id']}/history").json()
    assert hist[-1]["new_value"] == "27.8" and "recalculated" in hist[-1]["reason"]


def test_null_stat_is_not_available_not_pass():
    assert dash_mod._status(float("nan"), float("nan")) == "not_available"
    assert dash_mod._status(None, None) == "not_available"
    assert dash_mod._status(1.0, None) == "not_available"
    assert dash_mod._status(float("nan"), 1.0) == "not_available"
    assert dash_mod._status(1.0, 1.0) == "pass"
    assert dash_mod._status(1.0, 2.0) == "fail"


def test_null_stat_on_the_dashboard_is_grey(client, demo_accounts):
    pid, sponsor, _, row = _entered()
    sponsor.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]})
    stats = {s["name"]: s for s in sponsor.get(f"/api/dashboard/{pid}").json()["stats"]}
    assert stats["mean_change_systolic"]["status"] == "not_available"
    assert stats["mean_change_systolic"]["pass"] is False


def test_seed_refuses_without_locked_form(client, demo_accounts):
    pid = sponsor_draft()
    login(client, APPROVER)
    assert client.post(f"/api/data/seed/{pid}").status_code == 409


def test_seed_handles_subject_with_no_readings(client, demo_accounts):
    pid = sponsor_draft()
    sponsor = lock_and_assign(pid, "BGH", "MRC")
    bgh = site_client(BGH)
    assert bgh.post(f"/api/studies/{pid}/subjects").json()["code"] == "BGH-001"
    r = sponsor.post(f"/api/data/seed/{pid}")
    assert r.status_code == 200 and r.json()["seeded"] > 0
    with db.session() as s:
        statuses = set(s.scalars(select(Observation.status)))
    assert statuses == {"submitted"}, "seeded rows are never approved"


def test_unassign_site_with_data_needs_force(client, demo_accounts):
    pid, sponsor, _, _ = _entered()
    bgh_id = _org_id("BGH")
    r = sponsor.delete(f"/api/protocols/{pid}/sites/{bgh_id}")
    assert r.status_code == 409 and r.json()["detail"]["count"] == 1 and r.json()["detail"]["subjects"] == 1
    assert sponsor.delete(f"/api/protocols/{pid}/sites/{_org_id('MRC')}").status_code == 200, "no data, no fuss"
    assert sponsor.delete(f"/api/protocols/{pid}/sites/{bgh_id}?force=true").json() == {"assigned": False}
    assert len(sponsor.get(f"/api/protocols/{pid}/data").json()) == 1, "rows stay"


def test_forced_reextraction_refreshes_cache(client, demo_accounts, fake_llm):  # noqa: F811
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    assert _run(client, pid).status_code == 200
    made = len(fake_llm.calls)
    with db.session() as s:
        for row in s.scalars(select(LLMCall)):
            row.usage_json = {"marker": "stale"}
    r = _run(client, pid, force="true")
    assert r.status_code == 200 and len(fake_llm.calls) == 2 * made, "force goes to the provider"
    with db.session() as s:
        assert all("marker" not in row.usage_json for row in s.scalars(select(LLMCall)))


def test_unsupported_route_is_scoped_and_404s(client, demo_accounts):
    pid, sponsor, bgh, _ = _entered()
    assert sponsor.post("/api/dashboard/999999/unsupported?name=anything").status_code == 404
    assert sponsor.post(f"/api/dashboard/{pid}/unsupported?name=percent_missing").status_code == 400
    assert sponsor.post(f"/api/dashboard/{pid}/unsupported?name=breakdown_by_age").status_code == 403
    assert bgh.post(f"/api/dashboard/{pid}/unsupported?name=anything").status_code == 403


def test_prod_refuses_default_secret():
    prod = replace(config, env="prod")
    with pytest.raises(RuntimeError):
        check_production(replace(prod, secret_key=""))
    with pytest.raises(RuntimeError):
        check_production(replace(prod, secret_key=DEV_SECRET_KEY))
    check_production(replace(prod, secret_key="a-real-private-value"))
    check_production(replace(config, env="dev", secret_key=DEV_SECRET_KEY))
    assert docs_settings(prod) == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert docs_settings(replace(config, env="dev")) == {}


def test_subject_has_no_initials(client, demo_accounts):
    pid = sponsor_draft()
    lock_and_assign(pid, "BGH")
    bgh = site_client(BGH)
    row = bgh.post(f"/api/studies/{pid}/subjects").json()
    assert "initials" not in row
    assert bgh.post(f"/api/studies/{pid}/subjects", json={"initials": "JD"}).status_code == 422
    assert "initials" not in {c["name"] for c in inspect(db._engine).get_columns("subject")}


def test_cost_not_configured_when_prices_missing(client, demo_accounts, fake_llm, monkeypatch):  # noqa: F811
    monkeypatch.setattr(base_mod, "config", replace(
        base_mod.config, price_input_per_m=None, price_cached_input_per_m=0.01, price_output_per_m=0.5))
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    s = _run(client, pid).json()["summary"]
    assert s["input_tokens"] > 0 and s["est_cost_usd"] is None
