"""Sprint 3, stage 4: the Foundation form, field comments, the form audit trail."""

from conftest import APPROVER, BGH, BUILDER, login
from test_lock_sites_data import lock_and_assign, site_client, sponsor_draft

from ecrf import foundation
from ecrf.ingest import Document
from ecrf.schema import FieldDef, Source
from ecrf.verify import check_field

ORDER = ["Informed consent obtained", "Consent date", "Consent version", "Year of birth", "Age at consent",
         "Sex", "Race", "Ethnicity", "Height", "Weight", "BMI", "Eligible"]


def _draft(c, pid):
    return c.get(f"/api/protocols/{pid}/draft").json()


def _field(c, pid, visit, name):
    form = next(f for f in _draft(c, pid)["draft"]["forms"] if f["visit"] == visit)
    return next(x for x in form["fields"] if x["name"] == name)


def test_foundation_form_is_first_and_has_fixed_fields(client, demo_accounts):
    pid = sponsor_draft(approve_everything=False)
    login(client, BUILDER)
    forms = _draft(client, pid)["draft"]["forms"]
    assert forms[0]["visit"] == "Foundation"
    assert [f["name"] for f in forms[0]["fields"]] == ORDER
    codes = {f["name"]: f["cdash"] for f in forms[0]["fields"]}
    assert codes["Informed consent obtained"] == "DSDECOD" and codes["Consent date"] == "RFICDTC"
    assert codes["Year of birth"] == "BRTHDTC" and codes["Sex"] == "SEX" and codes["Race"] == "RACE"
    assert codes["Ethnicity"] == "ETHNIC" and codes["Height"] == "VSORRES/HEIGHT" and codes["Weight"] == "VSORRES/WEIGHT"
    assert codes["BMI"] == "BMI" and codes["Eligible"] == "IEYN"
    assert all(f["origin"] == "foundation" and f["source"]["section"] == "foundation" for f in forms[0]["fields"])
    assert all(f["origin"] == "model" for form in forms[1:] for f in form["fields"])
    # Added by code: the model's own counts are unaffected, and it is not a visit to choose.
    assert _draft(client, pid)["draft"]["summary"]["foundation_fields"] == len(ORDER)
    assert "Foundation" not in client.get(f"/api/protocols/{pid}/visits").json()["visits"]
    r = client.put(f"/api/protocols/{pid}/visits", json={"visits": ["Foundation", "Day 1"]})
    assert r.status_code == 422


def test_foundation_fields_skip_quote_verifier_only_by_origin():
    doc = Document(text="nothing about consent appears here")
    quote = Source(section="foundation", quote="Standard foundation field requested by sponsor")
    exempt = check_field(FieldDef(name="Sex", type="choice", source=quote, origin="foundation"), doc, 90)
    assert exempt.verdict == "unchecked" and exempt.status == "draft"
    # The same quote and name from the model is deleted like any other.
    model = check_field(FieldDef(name="Sex", type="choice", source=quote), doc, 90)
    assert model.verdict == "rejected"
    # The section label alone earns nothing.
    assert check_field(FieldDef(name="X", type="text", source=quote, origin="model"), doc, 90).verdict == "rejected"


def test_foundation_fields_cannot_be_deleted(client, demo_accounts):
    pid = sponsor_draft()
    login(client, BUILDER)

    def review(**change):
        return client.post(f"/api/protocols/{pid}/review", json={"changes": [{"visit": "Foundation", **change}]})

    assert review(name="Sex", status="rejected").status_code == 422
    assert review(name="Sex", new_name="Gender").status_code == 422
    assert review(name="Weight", type="text").status_code == 422
    assert review(name="Weight", collected=False).status_code == 422, "only race and ethnicity"
    assert review(name="Race", collected=False).status_code == 200
    assert _field(client, pid, "Foundation", "Race")["collected"] is False
    assert review(name="Ethnicity", collected=False).status_code == 200


def test_bmi_and_age_are_derived_from_foundation_fields(client, demo_accounts):
    pid = sponsor_draft()
    login(client, BUILDER)
    client.post(f"/api/protocols/{pid}/review", json={"changes": [
        {"visit": "Foundation", "name": "Race", "collected": False}], "action": "approve_all_remaining"})
    dm = lock_and_assign(pid, "BGH")
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects")

    def enter(readings):
        return bgh.post("/api/data/enter", json={
            "protocol_id": pid, "subject_id": "BGH-001", "visit": "Foundation",
            "readings": [{"field_name": k, "value": v} for k, v in readings.items()]})

    assert enter({"Height": 180, "Weight": 81, "Year of birth": 1970, "Consent date": "2026-03-01"}).status_code == 200
    rows = {r["field"]: r["value"] for r in dm.get(f"/api/protocols/{pid}/data").json()}
    assert rows["BMI"] == "25" and rows["Age at consent"] == "56"
    r = enter({"Age at consent": 40})
    assert r.status_code == 422 and "Age at consent" in str(r.json())
    r = enter({"BMI": 40})
    assert r.status_code == 422
    # A field not collected cannot be entered.
    assert enter({"Race": "ASIAN"}).status_code == 422


def test_reviewer_note_is_stored_as_comment(client, demo_accounts):
    pid = sponsor_draft()
    login(client, BUILDER)
    field = _field(client, pid, "Week 4", "Systolic Blood Pressure")
    r = client.post(f"/api/protocols/{pid}/review", json={"changes": [
        {"visit": "Week 4", "name": "Systolic Blood Pressure", "reviewer_note": "Check the range with Denise"}]})
    assert r.status_code == 200
    rows = client.get(f"/api/protocols/{pid}/comments").json()
    assert [(c["field_id"], c["body"], c["author"]) for c in rows] == [
        (field["field_id"], "Check the range with Denise", BUILDER)]
    # A comment made directly, then resolved, stays attached through a rename and a new version.
    c = client.post(f"/api/protocols/{pid}/comments", json={"field_id": field["field_id"], "body": "second"}).json()
    client.post(f"/api/protocols/{pid}/review", json={"changes": [
        {"visit": "Week 4", "name": "Systolic Blood Pressure", "new_name": "SBP"}]})
    assert _field(client, pid, "Week 4", "SBP")["field_id"] == field["field_id"]
    done = client.post(f"/api/protocols/{pid}/comments/{c['id']}/resolve").json()
    assert done["resolved_by"] == BUILDER and done["resolved_at"]
    assert client.post(f"/api/protocols/{pid}/comments", json={"field_id": "nope", "body": "x"}).status_code == 404
    assert client.post(f"/api/protocols/{pid}/comments", json={"field_id": field["field_id"], "body": " "}).status_code == 422


def test_field_edit_writes_old_and_new_values(client, demo_accounts):
    pid = sponsor_draft()
    login(client, BUILDER)
    field = _field(client, pid, "Week 4", "Systolic Blood Pressure")
    client.post(f"/api/protocols/{pid}/review", json={"note": "per Denise", "changes": [
        {"visit": "Week 4", "name": "Systolic Blood Pressure", "max": 199, "unit": "mmHg", "new_name": "SBP"}]})
    rows = client.get(f"/api/protocols/{pid}/form-history", params={"field_id": field["field_id"]}).json()
    by_attr = {h["attribute"]: h for h in rows}
    assert by_attr["name"]["old_value"] == "Systolic Blood Pressure" and by_attr["name"]["new_value"] == "SBP"
    assert by_attr["max"]["new_value"] == "199.0" and by_attr["max"]["by"] == BUILDER
    assert by_attr["max"]["reason"] == "per Denise" and by_attr["max"]["version"] == 3
    assert "unit" not in by_attr or by_attr["unit"]["old_value"] != by_attr["unit"]["new_value"]


def test_approve_and_reject_write_history(client, demo_accounts):
    pid = sponsor_draft(approve_everything=False)
    login(client, BUILDER)
    client.post(f"/api/protocols/{pid}/review", json={"changes": [
        {"visit": "Week 4", "name": "Systolic Blood Pressure", "status": "approved"},
        {"visit": "Screening", "name": "Position", "status": "rejected"}]})
    rows = client.get(f"/api/protocols/{pid}/form-history").json()
    assert {(h["old_value"], h["new_value"]) for h in rows if h["attribute"] == "status"} == {
        ("flagged", "approved"), ("draft", "rejected")}
    # The bulk action records each field too.
    before = len(rows)
    client.post(f"/api/protocols/{pid}/review", json={"changes": [], "action": "approve_all_remaining"})
    rows = client.get(f"/api/protocols/{pid}/form-history").json()
    assert len(rows) > before and rows[0]["reason"] == "approve all remaining"


def test_lock_writes_history_row(client, demo_accounts):
    pid = sponsor_draft()
    dm = lock_and_assign(pid)
    row = dm.get(f"/api/protocols/{pid}/form-history").json()[0]
    assert (row["attribute"], row["old_value"], row["new_value"], row["by"]) == ("state", "draft", "locked", APPROVER)
    assert row["field_id"] is None


def test_manual_cdash_code_is_saved_and_logged(client, demo_accounts):
    pid = sponsor_draft()
    login(client, BUILDER)
    library = client.get("/api/protocols/library/cdash").json()
    assert any(x["cdash"] == "SYSBP" for x in library)
    field = _field(client, pid, "Screening", "Position")
    assert field["cdash"] != "SEX"
    r = client.post(f"/api/protocols/{pid}/review", json={"changes": [
        {"visit": "Screening", "name": "Position", "cdash": "SEX"}]})
    assert r.status_code == 200
    now = _field(client, pid, "Screening", "Position")
    assert now["cdash"] == "SEX" and now["domain"] == "DM"
    rows = client.get(f"/api/protocols/{pid}/form-history", params={"field_id": field["field_id"]}).json()
    assert any(h["attribute"] == "cdash" and h["new_value"] == "SEX" for h in rows)
    r = client.post(f"/api/protocols/{pid}/review", json={"changes": [
        {"visit": "Screening", "name": "Position", "cdash": "MADEUP"}]})
    assert r.status_code == 422


def test_sites_do_not_see_comments_or_form_history(client, demo_accounts):
    pid = sponsor_draft()
    lock_and_assign(pid, "BGH")
    bgh = site_client(BGH)
    assert bgh.get(f"/api/protocols/{pid}/comments").status_code == 403
    assert bgh.get(f"/api/protocols/{pid}/form-history").status_code == 403
    assert foundation.VISIT == "Foundation"
