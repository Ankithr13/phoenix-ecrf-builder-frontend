"""Sprint 3 fixes: gaps found against the client's documents."""

import runpy
from pathlib import Path

import pytest
from conftest import ADMIN, AUDITOR, BGH, BUILDER
from sqlalchemy import select
from test_lock_sites_data import (
    SBP,
    _org_id,
    entry,
    lock_and_assign,
    site_client,
    sponsor_draft,
    submit,
)

from ecrf.checks import builtin
from ecrf.storage import db
from ecrf.storage.models import Observation, ObservationHistory, Query

MIGRATION = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0016_edit_check_owners.py"


def _site():
    pid = sponsor_draft()
    dm = lock_and_assign(pid, "BGH")
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects")
    return pid, dm, bgh


# ------------------------------------- Fix 3: the builder and subject-level data

def test_builder_has_no_page_status_or_listing(client, demo_accounts):
    pid, _dm, bgh = _site()
    bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130))
    submit(bgh, pid, "BGH-001")
    with db.session() as s:
        s.add(Query(protocol_id=pid, site_org_id=_org_id("BGH"), raised_by=BGH, raised_by_org="site",
                    text="Is the schedule in section 5 current?", status="open"))

    builder = site_client(BUILDER)
    assert builder.get(f"/api/dashboard/{pid}/page-status").status_code == 403
    assert builder.get(f"/api/listing/{pid}").status_code == 403
    assert builder.get(f"/api/listing/{pid}/Foundation").status_code == 403
    assert builder.get(f"/api/listing/{pid}/Foundation/export").status_code == 403

    # Results stay, and Queries 360 shows only the query about the form.
    assert builder.get(f"/api/dashboard/{pid}").status_code == 200
    assert builder.get(f"/api/dashboard/{pid}/queries").json()["counts"]["open"] == 1
    assert site_client(ADMIN).get(f"/api/dashboard/{pid}/queries").json()["counts"]["open"] > 1


def test_admin_and_read_only_keep_page_status(client, demo_accounts):
    pid, _dm, _bgh = _site()
    for email in (ADMIN, AUDITOR):
        r = site_client(email).get(f"/api/dashboard/{pid}/page-status")
        assert r.status_code == 200, email
        assert r.json()["sites"][0]["subjects"][0]["code"] == "BGH-001"


# ------------------------------------------------- Fix 4: a visit not performed

def _not_done(pid, reason="Patient did not attend", subject="BGH-001", visit="Week 4", extra=None):
    return {"protocol_id": pid, "subject_id": subject, "visit": visit, "reason": extra,
            "readings": [{"field_name": "Visit date", "completion_status": "not_done", "completion_reason": reason}]}


def _visit_rows(pid, visit="Week 4"):
    with db.session() as s:
        rows = s.scalars(select(Observation).where(Observation.protocol_id == pid, Observation.visit == visit)).all()
        history = {o.id: s.scalars(select(ObservationHistory).where(ObservationHistory.observation_id == o.id)).all()
                   for o in rows}
        return ([(o.field_name, o.repeat_num, o.completion_status, o.completion_reason, o.value_num) for o in rows],
                {(o.field_name, o.repeat_num): [(h.old_value, h.new_value, h.reason) for h in history[o.id]] for o in rows})


def test_visit_date_not_done_requires_reason(client, demo_accounts):
    pid, _dm, bgh = _site()
    r = bgh.post("/api/data/enter", json=_not_done(pid, reason=" "))
    assert r.status_code == 422 and "needs a reason" in r.text
    assert _visit_rows(pid)[0] == [], "nothing is saved or cascaded"


def test_ec_005_is_satisfied_by_visit_not_done(client, demo_accounts):
    pid, dm, bgh = _site()
    forms = dm.get(f"/api/protocols/{pid}/draft").json()["draft"]["forms"]
    field = next(f for form in forms if form["visit"] == "Week 4" for f in form["fields"] if f["name"] == "Visit date")
    assert field["allow_not_done"] is True

    assert bgh.post("/api/data/enter", json=_not_done(pid)).status_code == 200
    raised = submit(bgh, pid, "BGH-001")["queries"]
    assert not [q for q in raised if q["code"] == "EC-005"]
    assert raised == [], "the fields of a visit that did not happen raise nothing"

    # Without it, the check still fires, with the spec's words.
    bgh.post(f"/api/studies/{pid}/subjects")
    bgh.post("/api/data/enter", json=entry(pid, "BGH-002", 130))
    fired = [q for q in submit(bgh, pid, "BGH-002")["queries"] if q["code"] == "EC-005"]
    assert fired and fired[0]["text"] == "Enter visit date or document visit not performed."


def test_visit_not_done_cascades_with_history(client, demo_accounts):
    pid, dm, bgh = _site()
    # A value already there is replaced, and its history keeps it.
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130)).status_code == 200
    assert bgh.post("/api/data/enter", json=_not_done(pid)).status_code == 200

    rows, history = _visit_rows(pid)
    forms = dm.get(f"/api/protocols/{pid}/draft").json()["draft"]["forms"]
    fields = next(form for form in forms if form["visit"] == "Week 4")["fields"]
    live = [f for f in fields if f["status"] == "approved" and f["collected"]]
    assert len(rows) == sum(max(1, f["repeats"]) for f in live)
    for name, _rep, status, why, num in rows:
        if name == "Visit date":
            assert (status, why) == ("not_done", "Patient did not attend")
        else:
            assert (status, why, num) == ("not_applicable", "Visit not performed", None)
    assert history[(SBP, 1)][-1] == ("130", "Not applicable: Visit not performed", "Patient did not attend")
    assert history[(SBP, 2)] == [(None, "Not applicable: Visit not performed", "Visit not performed")]

    # Correcting the date lifts only what the cascade put there.
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", "2026-03-01", field="Visit date")).status_code == 200
    rows, history = _visit_rows(pid)
    assert all(status == "value" for _, _, status, _, _ in rows)
    assert history[(SBP, 1)][-1][1] in (None, "")


def test_visit_not_done_needs_sponsor_query_on_approved_values(client, demo_accounts):
    pid, dm, bgh = _site()
    bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130))
    submit(bgh, pid, "BGH-001")
    for q in dm.get("/api/queries").json():
        dm.post(f"/api/queries/{q['id']}/close", json={"reason": "not needed for this test"})
    ids = [r["id"] for r in dm.get(f"/api/protocols/{pid}/data").json()]
    assert dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": ids}).status_code == 200
    r = bgh.post("/api/data/enter", json=_not_done(pid))
    assert r.status_code == 409 and "approved" in r.text
    rows, _ = _visit_rows(pid)
    assert [x[2] for x in rows] == ["value"], "nothing changed"


# ----------------------------------------------------- Fix 5: edit check owners

SPEC_OWNERS = {"EC-001": "DM", "EC-002": "DM", "EC-003": "DM/Monitor", "EC-004": "DM/Clinical", "EC-005": "Site",
               "EC-006": "DM", "EC-007": "DM", "EC-008": "DM", "EC-009": "Safety/DM", "EC-010": "DM", "EC-012": "DM"}


@pytest.mark.parametrize("code", sorted(SPEC_OWNERS))
def test_builtin_check_owners_match_spec(code):
    assert builtin.OWNERS[code] == SPEC_OWNERS[code]


def test_generated_checks_carry_their_owner(client, demo_accounts):
    pid, dm, _bgh = _site()
    rows = dm.get(f"/api/protocols/{pid}/checks").json()
    made = {c["code"]: c["owner"] for c in rows}
    assert made["EC-005"] == "Site" and made["EC-001"] == "DM" and made["REQ"] == "DM"
    assert "system" not in made.values()


def test_migration_owner_table_matches_spec():
    upgrade = runpy.run_path(str(MIGRATION))
    assert upgrade["OWNERS"]["EC-009"] == "Safety/DM"
    assert {k: upgrade["OWNERS"][k] for k in SPEC_OWNERS} == SPEC_OWNERS
