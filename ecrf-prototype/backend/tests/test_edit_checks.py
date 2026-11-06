"""Sprint 3, stage 5: submit, edit checks, system queries, completion status."""

import os

import pytest
import yaml
from conftest import APPROVER, BGH, BUILDER, login
from test_lock_sites_data import (
    SBP,
    entry,
    lock_and_assign,
    people,
    site_client,
    sponsor_draft,
    submit,
)

from ecrf import foundation
from ecrf.checks import builtin, engine, run
from ecrf.config import config
from ecrf.schema import DraftECRF, FieldDef, Source, VisitForm

SRC = Source(section="1", quote="a quote that is long enough to pass")


def _f(name, type_="decimal", code=None, **kw):
    return FieldDef(name=name, type=type_, cdash=code, source=SRC, status="approved", **kw)


def _draft(*visits):
    forms = [foundation.form()]
    for visit, fields in visits:
        forms.append(VisitForm(visit=visit, fields=[foundation.visit_date(), *fields]))
    for f in forms[0].fields:
        f.status = "approved"
    return DraftECRF(protocol_id=1, protocol_hash="x", backend="t", model="t", forms=forms)


def _fails(draft, code, answers):
    """Which checks with this code fail for these (visit, name) answers."""
    ctx = run.context_from(draft, {(v, n, 1): (val, "value") for (v, n), val in answers.items()})
    return [hit for spec in builtin.specs(draft) if spec.code == code and (hit := engine.evaluate(spec, ctx))]


def _site():
    """A locked sample assigned to Boston General, with one patient."""
    pid = sponsor_draft()
    dm = lock_and_assign(pid, "BGH")
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects", json={"birth_year": 1970, "sex": "Male"})
    return pid, dm, bgh


# ----------------------------------------------------------------- submit

def test_submit_moves_draft_to_submitted_and_runs_checks(client, demo_accounts):
    pid, dm, bgh = _site()
    assert bgh.post("/api/data/submit", json={"protocol_id": pid, "subject_id": "BGH-001", "visit": "Week 4"}).status_code == 422
    bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130))
    assert bgh.get(f"/api/protocols/{pid}/data").json()[0]["status"] == "draft"
    assert dm.get(f"/api/protocols/{pid}/data").json() == []
    r = submit(bgh, pid, "BGH-001")
    assert r["submitted"] == 1 and any(q["code"] == "EC-005" for q in r["queries"]), "no visit date was entered"
    assert dm.get(f"/api/protocols/{pid}/data").json()[0]["status"] == "submitted"
    # Permission: the data manager cannot submit a site's data.
    assert dm.post("/api/data/submit", json={"protocol_id": pid, "subject_id": "BGH-001", "visit": "Week 4"}).status_code == 403


def test_hard_check_blocks_submit(client, demo_accounts):
    pid, dm, bgh = _site()
    bgh.post("/api/data/enter", json=entry(pid, "BGH-001", "v1", visit="Foundation", field="Consent version"))
    draft = dm.get(f"/api/protocols/{pid}/draft").json()["draft"]
    version = next(f for f in draft["forms"][0]["fields"] if f["name"] == "Consent version")
    r = dm.post(f"/api/protocols/{pid}/checks", json={
        "type": "format", "severity": "hard", "form": "Foundation", "field_ids": [version["field_id"]],
        "logic": {"kind": "pattern", "pattern": r"V\d+\.\d+"}, "message": "Consent version looks like V1.0"})
    assert r.status_code == 200, r.text
    body = {"protocol_id": pid, "subject_id": "BGH-001", "visit": "Foundation"}
    r = bgh.post("/api/data/submit", json=body)
    assert r.status_code == 422 and "Consent version#1" in r.json()["detail"]["errors"]
    assert bgh.get(f"/api/protocols/{pid}/data").json()[0]["status"] == "draft", "nothing moved"
    # A hard check blocks the save too; a good value then submits.
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", "bad", visit="Foundation", field="Consent version")).status_code == 422
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", "V1.0", visit="Foundation", field="Consent version")).status_code == 200
    assert bgh.post("/api/data/submit", json=body).status_code == 200


def test_soft_check_raises_system_query_once(client, demo_accounts):
    pid, dm, bgh = _site()
    r = bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 400))
    assert r.status_code == 200, "out of range is saved; checks never overwrite data"
    first = [q for q in submit(bgh, pid, "BGH-001")["queries"] if q["code"] == "EC-006"]
    assert len(first) == 1
    q = next(x for x in dm.get("/api/queries").json() if x["check_code"] == "EC-006")
    assert q["raised_by"] == "system" and q["status"] == "open" and q["about"] == "value" and q["value"] == "400"
    assert "outside the expected range" in q["text"]
    assert submit(bgh, pid, "BGH-001")["queries"] == [], "no second query while one is live"
    row = dm.get(f"/api/protocols/{pid}/data").json()[0]
    assert row["open_query_count"] == 1
    assert dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]}).status_code == 409


def test_system_query_auto_answers_when_fixed(client, demo_accounts):
    pid, dm, bgh = _site()
    bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 400))
    submit(bgh, pid, "BGH-001")
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 140, reason="typing slip")).status_code == 200
    q = next(x for x in dm.get("/api/queries").json() if x["check_code"] == "EC-006")
    assert q["status"] == "answered" and q["answer_text"] == run.AUTO_ANSWER and q["answered_by"] == "system"
    assert q["can_close"] is True, "left for the data manager to close"
    row = dm.get(f"/api/protocols/{pid}/data").json()[0]
    assert dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]}).status_code == 409
    assert dm.post(f"/api/queries/{q['id']}/close").status_code == 200
    assert dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]}).status_code == 200
    # Broken again: the check raises afresh once the old query is closed.
    dm.post(f"/api/data/{row['id']}/queries", json={"text": "re-check"})
    bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 500, reason="re-measured"))
    assert any(x["check_code"] == "EC-006" and x["status"] == "open" for x in dm.get("/api/queries").json())


def test_edit_after_submit_requires_reason(client, demo_accounts):
    pid, dm, bgh = _site()
    bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130))
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 131)).status_code == 200, "a draft needs no reason"
    submit(bgh, pid, "BGH-001")
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 132)).status_code == 422
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 132, reason="no")).status_code == 422, "too short"
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 132, reason="re-read the chart")).status_code == 200
    row = dm.get(f"/api/protocols/{pid}/data").json()[0]
    hist = dm.get(f"/api/protocols/{pid}/data/{row['id']}/history").json()
    assert hist[-1]["reason"] == "re-read the chart" and hist[-1]["old_value"] == "131"
    assert row["status"] == "submitted"


def test_not_done_requires_reason_and_permission_on_field(client, demo_accounts):
    pid = sponsor_draft()
    b = site_client(BUILDER)
    assert b.post(f"/api/protocols/{pid}/review", json={"changes": [
        {"visit": "Week 4", "name": "HbA1c", "allow_unknown": True}]}).status_code == 200
    dm = lock_and_assign(pid, "BGH")
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects")

    def post(field, **reading):
        return bgh.post("/api/data/enter", json={"protocol_id": pid, "subject_id": "BGH-001", "visit": "Week 4",
                                                 "readings": [{"field_name": field, **reading}]})

    assert post(SBP, completion_status="not_done", completion_reason="refused").status_code == 422, "not allowed here"
    assert post("HbA1c", completion_status="unknown").status_code == 422, "needs a reason"
    assert post("HbA1c", completion_status="unknown", completion_reason="monitor off", value=70).status_code == 422
    assert post("HbA1c", completion_status="unknown", completion_reason="monitor off").status_code == 200
    submit(bgh, pid, "BGH-001")
    row = next(r for r in dm.get(f"/api/protocols/{pid}/data").json() if r["field"] == "HbA1c")
    # A field marked unknown is answered, so nothing asks for it again.
    warnings = bgh.post("/api/data/validate", json={"protocol_id": pid, "subject_id": "BGH-001", "visit": "Week 4",
                                                    "readings": []}).json()["warnings"]
    assert not [w for w in warnings if w["field"] == "HbA1c"]
    assert row["completion_status"] == "unknown" and row["value"] == "Unknown: monitor off"
    # Procedures allow Not done by default; a measurement does not.
    fields = {f["name"]: f for f in dm.get(f"/api/protocols/{pid}/draft").json()["draft"]["forms"][1]["fields"]}
    assert fields["ECG Performed"]["allow_not_done"] is True and fields[SBP]["allow_not_done"] is False


# ------------------------------------------------------------ the checks

def test_builtin_checks_bind_by_cdash_code():
    draft = _draft(("Day 1", [_f("Top number", "integer", "SYSBP"), _f("Bottom number", "integer", "DIABP")]))
    assert _fails(draft, "EC-007", {("Day 1", "Top number"): 80, ("Day 1", "Bottom number"): 90})
    assert not _fails(draft, "EC-007", {("Day 1", "Top number"): 120, ("Day 1", "Bottom number"): 80})
    # Not on the form, no check.
    assert not [s for s in builtin.specs(_draft(("Day 1", []))) if s.code == "EC-007"]
    hard = {s.severity for s in builtin.specs(draft) if s.type == "format"}
    soft = {s.severity for s in builtin.specs(draft) if s.type != "format"}
    assert hard == {"hard"} and soft == {"soft"}


def test_ec_001():
    d = _draft()
    assert _fails(d, "EC-001", {})
    assert not _fails(d, "EC-001", {("Foundation", "Year of birth"): 1970})


def test_ec_002():
    d = _draft()
    a = {("Foundation", "Consent date"): "2026-03-01"}
    assert _fails(d, "EC-002", {**a, ("Foundation", "Year of birth"): 2026})
    assert not _fails(d, "EC-002", {**a, ("Foundation", "Year of birth"): 1970})


def test_ec_003():
    d = _draft(("Day 1", []))
    assert _fails(d, "EC-003", {("Foundation", "Consent date"): "2026-03-02", ("Day 1", "Visit date"): "2026-03-01"})
    assert not _fails(d, "EC-003", {("Foundation", "Consent date"): "2026-03-01", ("Day 1", "Visit date"): "2026-03-01"})


def test_ec_004():
    d = _draft(("Day 1", [_f("Weight", code="WEIGHT")]))
    assert _fails(d, "EC-004", {("Foundation", "Eligible"): "No", ("Day 1", "Weight"): 70})
    assert not _fails(d, "EC-004", {("Foundation", "Eligible"): "No"})
    assert not _fails(d, "EC-004", {("Foundation", "Eligible"): "Yes", ("Day 1", "Weight"): 70})


def test_ec_005():
    d = _draft(("Day 1", []))
    assert _fails(d, "EC-005", {})
    assert not _fails(d, "EC-005", {("Day 1", "Visit date"): "2026-03-01"})


def test_ec_006():
    d = _draft(("Day 1", [_f("SBP", "integer", "SYSBP", min=60, max=250), _f("No range", "integer")]))
    assert _fails(d, "EC-006", {("Day 1", "SBP"): 300})
    assert not _fails(d, "EC-006", {("Day 1", "SBP"): 120})
    assert not [s for s in builtin.specs(d) if s.code == "EC-006" and "No range" in s.message]


def test_ec_007():
    d = _draft(("Day 1", [_f("Systolic", "integer", "SYSBP"), _f("Diastolic", "integer", "DIABP")]))
    assert _fails(d, "EC-007", {("Day 1", "Systolic"): 80, ("Day 1", "Diastolic"): 80})
    assert not _fails(d, "EC-007", {("Day 1", "Systolic"): 120})


def test_ec_008():
    d = _draft(("Day 1", [_f("AE start", "date", "AESTDTC"), _f("AE end", "date", "AEENDTC")]))
    assert _fails(d, "EC-008", {("Day 1", "AE start"): "2026-03-02", ("Day 1", "AE end"): "2026-03-01"})
    assert not _fails(d, "EC-008", {("Day 1", "AE start"): "2026-03-01", ("Day 1", "AE end"): "2026-03-01"})


def test_ec_009():
    d = _draft(("Day 1", [_f("Serious", "boolean", "AESER"), _f("Hospitalised", "boolean", "AESHOSP")]))
    assert _fails(d, "EC-009", {("Day 1", "Serious"): "Yes"})
    assert not _fails(d, "EC-009", {("Day 1", "Serious"): "Yes", ("Day 1", "Hospitalised"): "Yes"})
    assert not _fails(d, "EC-009", {("Day 1", "Serious"): "No"})


def test_ec_010():
    d = _draft(("Day 1", [_f("Med start", "date", "CMSTDTC"), _f("Med stop", "date", "CMENDTC")]))
    assert _fails(d, "EC-010", {("Day 1", "Med start"): "2026-03-02", ("Day 1", "Med stop"): "2026-03-01"})
    assert not _fails(d, "EC-010", {("Day 1", "Med start"): "2026-03-01", ("Day 1", "Med stop"): "2026-03-02"})


@pytest.mark.skip(reason="EC-011, administration without a visit, needs an intervention form this system does not model")
def test_ec_011():
    pass


def test_ec_012():
    d = _draft(("End", [_f("Completion status", "choice", choices=["Completed"]), _f("Completion date", "date"),
                        _f("Completion reason", "text")]))
    assert _fails(d, "EC-012", {("End", "Completion status"): "Completed"})
    assert _fails(d, "EC-012", {("End", "Completion status"): "Completed", ("End", "Completion date"): "2026-03-01"})
    assert not _fails(d, "EC-012", {("End", "Completion status"): "Completed", ("End", "Completion date"): "2026-03-01",
                                    ("End", "Completion reason"): "finished"})
    assert not _fails(d, "EC-012", {})


def test_not_done_counts_as_answered_for_required():
    d = _draft(("Day 1", []))
    ctx = run.context_from(d, {("Day 1", "Visit date", 1): (None, "not_done")})
    spec = next(s for s in builtin.specs(d) if s.code == "EC-005")
    assert engine.evaluate(spec, ctx) is None


def test_custom_check_crud_and_evaluation(client, demo_accounts):
    pid = sponsor_draft()
    b = site_client(BUILDER)
    draft = b.get(f"/api/protocols/{pid}/draft").json()["draft"]
    w4 = next(f for f in draft["forms"] if f["visit"] == "Week 4")
    hr = next(f for f in w4["fields"] if f["name"] == "Fasting Plasma Glucose")["field_id"]
    sbp = next(f for f in w4["fields"] if f["name"] == SBP)["field_id"]
    body = {"type": "cross_field", "form": "Week 4", "field_ids": [hr, sbp], "logic": {"a": hr, "b": sbp, "op": "<"},
            "message": "Glucose should be below systolic pressure"}
    # Try it before saving it.
    r = b.post(f"/api/protocols/{pid}/checks/test", json={**body, "sample": {hr: 200, sbp: 120}})
    assert r.json() == {"passes": False}
    assert b.post(f"/api/protocols/{pid}/checks/test", json={**body, "sample": {hr: 70, sbp: 120}}).json() == {"passes": True}
    assert b.post(f"/api/protocols/{pid}/checks/test", json={"type": "manual", "field_ids": [hr]}).json()["passes"] is None

    c = b.post(f"/api/protocols/{pid}/checks", json=body).json()
    assert c["code"] == "CUSTOM-1" and c["severity"] == "soft" and c["enabled"] is True
    assert b.post(f"/api/protocols/{pid}/checks", json={**body, "severity": "hard"}).status_code == 422, "only format is hard"
    assert b.post(f"/api/protocols/{pid}/checks", json={**body, "type": "nonsense"}).status_code == 422
    assert b.post(f"/api/protocols/{pid}/checks", json={**body, "field_ids": ["nope"]}).status_code == 422
    assert b.patch(f"/api/protocols/{pid}/checks/{c['id']}", json={"enabled": False}).json()["enabled"] is False
    b.patch(f"/api/protocols/{pid}/checks/{c['id']}", json={"enabled": True})

    dm = lock_and_assign(pid, "BGH")
    codes = {x["code"] for x in dm.get(f"/api/protocols/{pid}/checks").json()}
    assert {"CUSTOM-1", "EC-001", "EC-005", "EC-006", "EC-007", "FMT"} <= codes

    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects")
    for field, value in ((SBP, 120), ("Fasting Plasma Glucose", 200)):
        bgh.post("/api/data/enter", json=entry(pid, "BGH-001", value, field=field))
    assert any(q["code"] == "CUSTOM-1" for q in submit(bgh, pid, "BGH-001")["queries"])


def test_check_change_after_lock_needs_dm_and_is_logged(client, demo_accounts):
    pid = sponsor_draft()
    b = site_client(BUILDER)
    dm = lock_and_assign(pid)
    rows = dm.get(f"/api/protocols/{pid}/checks").json()
    ec6 = next(x for x in rows if x["code"] == "EC-006")
    assert b.patch(f"/api/protocols/{pid}/checks/{ec6['id']}", json={"enabled": False}).status_code == 403
    assert b.post(f"/api/protocols/{pid}/checks", json={"type": "manual", "field_ids": ec6["field_ids"], "message": "x"}).status_code == 403
    r = dm.patch(f"/api/protocols/{pid}/checks/{ec6['id']}", json={"enabled": False, "reason": "per Denise"})
    assert r.json()["enabled"] is False
    row = dm.get(f"/api/protocols/{pid}/form-history").json()[0]
    assert row["attribute"] == "edit_check:EC-006" and row["new_value"] == "enabled=False" and row["reason"] == "per Denise"
    fmt = next(x for x in rows if x["code"] == "FMT")
    assert dm.patch(f"/api/protocols/{pid}/checks/{fmt['id']}", json={"enabled": False}).status_code == 422
    # Manual checks are stored and never fire.
    r = dm.post(f"/api/protocols/{pid}/checks", json={"type": "manual", "field_ids": ec6["field_ids"], "message": "Look at the ECG"})
    assert r.status_code == 200
    login(client, APPROVER)
    assert dm.get(f"/api/protocols/{pid}/form-history").json()[0]["new_value"].startswith("added: manual")


def test_lab_reference_rows_all_have_source(client, demo_accounts):
    with open(os.path.join(config.data_dir, "lab_reference_ranges.yaml")) as f:
        rows = yaml.safe_load(f)["analytes"]
    assert 0 < len(rows) <= 20
    for row in rows:
        assert row["source"].startswith("https://"), row["name"]
        assert row["status"] == "unconfirmed", row["name"]
        assert row["unit"] and row["low"] < row["high"], row["name"]
    login(client, BUILDER)
    assert client.get("/api/protocols/library/lab-ranges").json()[0]["name"] == rows[0]["name"]


def test_filters_return_expected_subjects(client, demo_accounts):
    pid, dm, bgh = _site()
    bgh.post(f"/api/studies/{pid}/subjects")
    bgh.post(f"/api/studies/{pid}/subjects")
    bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130))              # draft
    bgh.post("/api/data/enter", json=entry(pid, "BGH-002", 400))              # submitted, out of range
    submit(bgh, pid, "BGH-002")

    def codes(**params):
        return [x["code"] for x in bgh.get(f"/api/studies/{pid}/subjects", params=params).json()]

    assert codes() == ["BGH-001", "BGH-002", "BGH-003"]
    assert codes(status="draft") == ["BGH-001"]
    assert codes(status="submitted") == ["BGH-002"]
    assert codes(status="approved") == []
    assert codes(visit="Week 4") == ["BGH-001", "BGH-002"]
    assert codes(visit="Day 1") == []
    assert codes(open_queries=True) == ["BGH-002"]
    assert codes(needs_signoff=True) == []
    # Close what the checks raised, approve, and the visit is ready for sign-off.
    for q in people(dm.get("/api/queries").json()) + dm.get("/api/queries").json():
        dm.post(f"/api/queries/{q['id']}/close")
    row = dm.get(f"/api/protocols/{pid}/data").json()[0]
    assert dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]}).status_code == 200
    assert codes(needs_signoff=True) == ["BGH-002"]
    # A sponsor never sees a draft, in the list or by filter.
    assert [x["code"] for x in dm.get(f"/api/studies/{pid}/subjects", params={"status": "draft"}).json()] == []
