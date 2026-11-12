"""Sprint 3, stage 6: query lifecycle, monitor review, sign-off, study lock, notifications."""

import pytest
from conftest import ADMIN, APPROVER, BGH, BUILDER, MONITOR, MRC, PASSWORD, PI
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

from ecrf import notify
from ecrf.storage import db
from ecrf.storage.models import Notification, Protocol, User


def _entered(value=130, monitor=False, signature=True):
    """A locked sample at Boston General, one value entered and submitted."""
    pid = sponsor_draft()
    dm = lock_and_assign(pid, "BGH")
    admin = site_client(ADMIN)
    admin.put(f"/api/admin/chain/{pid}", json={"monitor_review_required": monitor,
                                               "investigator_signature_required": signature})
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects")
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", value)).status_code == 200
    submit(bgh, pid, "BGH-001")
    return pid, dm, bgh, dm.get(f"/api/protocols/{pid}/data").json()[0]


def _clear_queries(dm):
    for q in dm.get("/api/queries").json():
        if q["status"] in ("open", "answered"):
            dm.post(f"/api/queries/{q['id']}/close", json={"reason": "not needed for this test"})


def _approved_and_clear():
    pid, dm, bgh, row = _entered()
    _clear_queries(dm)
    assert dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]}).status_code == 200
    return pid, dm, bgh, row


def _sign(pi, pid, password=PASSWORD, visit="Week 4"):
    return pi.post(f"/api/protocols/{pid}/signoff", json={"subject_id": "BGH-001", "visit": visit, "password": password})


# ---------------------------------------------------------------- queries

def test_query_status_transitions(client, demo_accounts):
    _pid, dm, bgh, row = _entered()
    q = dm.post(f"/api/data/{row['id']}/queries", json={"text": "please check"}).json()
    assert q["status"] == "open" and q["raised_by_role"] == "data_manager" and q["can_cancel"] is True
    r = bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "checked"}).json()
    assert r["status"] == "answered" and r["answered_at"]
    r = dm.post(f"/api/queries/{q['id']}/close", json={"reason": "fine as it is"}).json()
    assert r["status"] == "closed" and r["closed_at"] and r["close_reason"] == "fine as it is"
    # Closed is final.
    assert bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "more"}).status_code == 409
    assert dm.post(f"/api/queries/{q['id']}/cancel", json={"reason": "too late"}).status_code == 409


def test_close_with_unchanged_value_needs_reason(client, demo_accounts):
    pid, dm, bgh, row = _entered()
    q = dm.post(f"/api/data/{row['id']}/queries", json={"text": "please check"}).json()
    assert q["needs_close_reason"] is True
    assert dm.post(f"/api/queries/{q['id']}/close").status_code == 422
    assert dm.post(f"/api/queries/{q['id']}/close", json={"reason": " "}).status_code == 422
    # Once the value changes, no reason is needed.
    assert bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "was 138", "new_value": 138}).json()["needs_close_reason"] is False
    assert dm.post(f"/api/queries/{q['id']}/close").json()["status"] == "closed"
    # A query about the study has no value, so nothing to explain.
    g = dm.post("/api/queries", json={"protocol_id": pid, "site_org_id": _org_id("BGH"), "text": "Enrolment?"}).json()
    assert g["needs_close_reason"] is False and dm.post(f"/api/queries/{g['id']}/close").status_code == 200


def test_cancel_needs_reason_and_raiser(client, demo_accounts):
    _pid, dm, bgh, row = _entered()
    q = dm.post(f"/api/data/{row['id']}/queries", json={"text": "please check"}).json()
    monitor = site_client(MONITOR)
    assert monitor.post(f"/api/queries/{q['id']}/cancel", json={"reason": "not mine"}).status_code == 403
    assert bgh.post(f"/api/queries/{q['id']}/cancel", json={"reason": "not mine"}).status_code == 403
    assert dm.post(f"/api/queries/{q['id']}/cancel", json={"reason": "  "}).status_code == 422
    r = dm.post(f"/api/queries/{q['id']}/cancel", json={"reason": "raised on the wrong value"}).json()
    assert r["status"] == "cancelled" and r["cancel_reason"] == "raised on the wrong value" and r["cancelled_at"]
    assert r["open_query_count"] == 0, "a cancelled query no longer blocks approval"
    # A site cannot cancel its own either, and a query it raised stays with the sponsor to settle.
    s = bgh.post(f"/api/data/{row['id']}/queries", json={"text": "which unit?"}).json()
    assert s["can_cancel"] is False and bgh.post(f"/api/queries/{s['id']}/cancel", json={"reason": "x"}).status_code == 403


# ----------------------------------------------------------- monitor review

def test_monitor_review_gate_when_required(client, demo_accounts):
    pid, dm, _bgh, row = _entered(monitor=True)
    _clear_queries(dm)
    r = dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]})
    assert r.status_code == 409 and r.json()["detail"]["unreviewed"] == [row["id"]]
    body = {"subject_id": "BGH-001", "visit": "Week 4"}
    assert dm.post(f"/api/protocols/{pid}/monitor-review", json=body).status_code == 403, "the monitor's job"
    monitor = site_client(MONITOR)
    assert monitor.post(f"/api/protocols/{pid}/monitor-review", json=body).json() == {"reviewed": 1}
    assert dm.get(f"/api/protocols/{pid}/data").json()[0]["status"] == "monitor_reviewed"
    assert monitor.post(f"/api/protocols/{pid}/monitor-review", json=body).status_code == 409, "nothing left"
    assert dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]}).status_code == 200


def test_monitor_review_not_required_lets_approval_through(client, demo_accounts):
    pid, dm, _, row = _entered()
    _clear_queries(dm)
    assert dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]}).status_code == 200


# ----------------------------------------------------------------- sign-off

def test_signoff_blocked_by_open_query(client, demo_accounts):
    pid, dm, bgh, _ = _approved_and_clear()
    pi = site_client(PI)
    g = bgh.post("/api/queries", json={"protocol_id": pid, "subject_code": "BGH-001", "text": "A question"}).json()
    r = _sign(pi, pid)
    assert r.status_code == 409 and r.json()["detail"]["open_queries"] == 1
    dm.post(f"/api/queries/{g['id']}/close")
    assert _sign(pi, pid).status_code == 200


def test_signoff_needs_all_values_approved(client, demo_accounts):
    pid, dm, _bgh, row = _entered()
    _clear_queries(dm)
    pi = site_client(PI)
    r = _sign(pi, pid)
    assert r.status_code == 409 and r.json()["detail"]["waiting"] == [SBP]
    dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]})
    assert _sign(pi, pid).status_code == 200
    assert _sign(pi, pid, visit="Day 1").status_code == 409, "nothing entered there"
    assert _sign(site_client(BGH), pid).status_code == 403, "signature authority is the investigator's"


def test_signoff_reenters_password(client, demo_accounts):
    pid, _, _, _ = _approved_and_clear()
    pi = site_client(PI)
    assert _sign(pi, pid, password="wrong").status_code == 403
    r = _sign(pi, pid)
    assert r.status_code == 200 and r.json()["signed_by"] == PI
    assert "complete and accurate" in r.json()["meaning"]
    assert _sign(pi, pid).status_code == 409, "already signed"
    rows = pi.get(f"/api/protocols/{pid}/signoffs").json()["rows"]
    assert [x["visit"] for x in rows] == ["Week 4"]


def test_signoff_not_required_refuses(client, demo_accounts):
    pid, dm, _, row = _entered(signature=False)
    _clear_queries(dm)
    dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]})
    assert _sign(site_client(PI), pid).status_code == 409


def test_edit_after_signoff_invalidates_it(client, demo_accounts):
    pid, dm, bgh, row = _approved_and_clear()
    pi = site_client(PI)
    assert _sign(pi, pid).status_code == 200
    subject = lambda: dm.get(f"/api/studies/{pid}/subjects").json()[0]  # noqa: E731
    assert subject()["needs_signoff"] is False
    q = dm.post(f"/api/data/{row['id']}/queries", json={"text": "re-check please"}).json()
    assert bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "was 138", "new_value": 138}).status_code == 200
    rows = pi.get(f"/api/protocols/{pid}/signoffs").json()["rows"]
    assert rows[0]["invalidated_at"], "the row stays, marked"
    assert subject()["needs_resign"] == ["Week 4"]
    dm.post(f"/api/queries/{q['id']}/close")
    dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]})
    assert subject()["needs_signoff"] is True
    assert _sign(pi, pid).status_code == 200, "and it can be signed again"
    assert subject()["needs_resign"] == []


# --------------------------------------------------------------- study lock

def test_study_lock_needs_all_signoffs_and_no_open_queries(client, demo_accounts):
    pid, dm, _bgh, row = _entered()
    r = dm.post(f"/api/protocols/{pid}/study-lock")
    assert r.status_code == 409
    text = " ".join(r.json()["detail"]["blockers"])
    assert "open quer" in text and "not approved" in text and "not signed" in text
    _clear_queries(dm)
    dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]})
    r = dm.post(f"/api/protocols/{pid}/study-lock")
    assert r.status_code == 409 and r.json()["detail"]["blockers"] == ["1 visit(s) not signed: BGH-001 Week 4"]
    _sign(site_client(PI), pid)
    assert dm.get(f"/api/protocols/{pid}/study-lock").json()["blockers"] == []
    assert site_client(BUILDER).post(f"/api/protocols/{pid}/study-lock").status_code == 403
    r = dm.post(f"/api/protocols/{pid}/study-lock")
    assert r.status_code == 200 and r.json()["locked_by"] == APPROVER
    row = dm.get(f"/api/protocols/{pid}/form-history").json()[0]
    assert row["attribute"] == "study_lock" and row["new_value"] == "locked"


def test_study_lock_without_signature_needs_only_approval(client, demo_accounts):
    pid, dm, _, row = _entered(signature=False)
    _clear_queries(dm)
    dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]})
    assert dm.post(f"/api/protocols/{pid}/study-lock").status_code == 200


def _ready_to_lock():
    """Approved, no open query, no sign-off required: nothing blocks the lock."""
    pid, dm, _, row = _entered(signature=False)
    _clear_queries(dm)
    dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": [row["id"]]})
    assert dm.get(f"/api/protocols/{pid}/study-lock").json()["blockers"] == []
    return pid, dm


def test_admin_cannot_lock_study(client, demo_accounts):
    pid, _dm = _ready_to_lock()
    admin = site_client(ADMIN)
    assert admin.post(f"/api/protocols/{pid}/study-lock").status_code == 403
    assert admin.get(f"/api/protocols/{pid}/study-lock").status_code == 403
    with db.session() as s:
        assert s.get(Protocol, pid).study_locked_at is None


def test_data_manager_can_still_lock_study(client, demo_accounts):
    pid, dm = _ready_to_lock()
    r = dm.post(f"/api/protocols/{pid}/study-lock")
    assert r.status_code == 200 and r.json()["locked_by"] == APPROVER


def test_study_lock_freezes_all_writes(client, demo_accounts):
    pid, dm, bgh, row = _approved_and_clear()
    pi = site_client(PI)
    _sign(pi, pid)
    assert dm.post(f"/api/protocols/{pid}/study-lock").status_code == 200
    body = {"protocol_id": pid, "subject_id": "BGH-001", "visit": "Week 4"}
    writes = [
        (bgh, "post", "/api/data/enter", entry(pid, "BGH-001", 140, reason="after the lock")),
        (bgh, "post", "/api/data/submit", body),
        (bgh, "post", f"/api/studies/{pid}/subjects", {}),
        (bgh, "post", f"/api/data/{row['id']}/queries", {"text": "?"}),
        (bgh, "post", "/api/queries", {"protocol_id": pid, "text": "?"}),
        (dm, "post", f"/api/protocols/{pid}/data/approve", {"observation_ids": [row["id"]]}),
        (dm, "post", f"/api/data/seed/{pid}", None),
        (dm, "post", f"/api/protocols/{pid}/sites", {"site_org_id": _org_id("MRC")}),
        (dm, "delete", f"/api/protocols/{pid}/sites/{_org_id('BGH')}", None),
        (site_client(MONITOR), "post", f"/api/protocols/{pid}/monitor-review", {"subject_id": "BGH-001", "visit": "Week 4"}),
        (pi, "post", f"/api/protocols/{pid}/signoff", {"subject_id": "BGH-001", "visit": "Week 4", "password": PASSWORD}),
    ]
    for c, method, url, data in writes:
        r = getattr(c, method)(url, json=data) if method != "delete" else c.delete(url)
        assert r.status_code == 409, f"{url}: {r.status_code} {r.text[:120]}"
    # Reading still works.
    assert dm.get(f"/api/protocols/{pid}/data").status_code == 200
    assert dm.get("/api/protocols").json()[0]["study_locked_at"]


# ------------------------------------------------------------ notifications

def _kinds(email):
    with db.session() as s:
        u = s.scalars(select(User).where(User.email == email)).first()
        return [n.kind for n in s.scalars(select(Notification).where(Notification.user_id == u.id))]


def _query_raised():
    _, dm, _, row = _entered()
    dm.post(f"/api/data/{row['id']}/queries", json={"text": "please check"})
    return BGH


def _query_answered():
    _, dm, bgh, row = _entered()
    q = dm.post(f"/api/data/{row['id']}/queries", json={"text": "please check"}).json()
    bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "fine"})
    return APPROVER


def _system_query():
    _entered(value=400)
    return BGH


def _visit_submitted():
    _entered()
    return APPROVER


def _visit_approved():
    _approved_and_clear()
    return BGH


def _signoff_needed():
    _approved_and_clear()
    return PI


def _signoff_invalidated():
    pid, dm, bgh, row = _approved_and_clear()
    _sign(site_client(PI), pid)
    q = dm.post(f"/api/data/{row['id']}/queries", json={"text": "re-check"}).json()
    bgh.post(f"/api/queries/{q['id']}/answer", json={"text": "was 138", "new_value": 138})
    return PI


def _form_locked():
    pid = sponsor_draft()
    lock_and_assign(pid, "BGH")
    return BGH


def _study_locked():
    pid, dm, _, _ = _approved_and_clear()
    _sign(site_client(PI), pid)
    dm.post(f"/api/protocols/{pid}/study-lock")
    return MONITOR


EVENTS = {"query_raised": _query_raised, "query_answered": _query_answered, "system_query": _system_query,
          "visit_submitted": _visit_submitted, "visit_approved": _visit_approved, "signoff_needed": _signoff_needed,
          "signoff_invalidated": _signoff_invalidated, "form_locked": _form_locked, "study_locked": _study_locked}


def test_every_kind_has_an_event():
    assert set(EVENTS) == set(notify.KINDS) and len(EVENTS) == 9


@pytest.mark.parametrize("kind", list(EVENTS))
def test_notifications_fire_for_each_event(client, demo_accounts, kind):
    who = EVENTS[kind]()
    assert kind in _kinds(who), f"{who} heard: {_kinds(who)}"


def test_notifications_stay_at_their_site(client, demo_accounts):
    _entered()
    assert _kinds(MRC) == [], "Mercy hears nothing about Boston General's study"


def test_admin_has_no_notifications_route(client, demo_accounts):
    admin = site_client(ADMIN)
    assert admin.get("/api/notifications").status_code == 403
    assert admin.get("/api/notifications/unread-count").status_code == 403
    assert admin.post("/api/notifications/read-all").status_code == 403
    assert admin.post("/api/notifications/1/read").status_code == 403


def test_no_notifications_created_for_admin(client, demo_accounts):
    # The admin is in the sponsor organisation, which hears about the study lock.
    pid, dm = _ready_to_lock()
    assert dm.post(f"/api/protocols/{pid}/study-lock").status_code == 200
    assert "study_locked" in _kinds(APPROVER)
    assert _kinds(ADMIN) == []


def test_notification_badge_counts_unread_only(client, demo_accounts):
    _pid, dm, bgh, row = _entered()
    dm.post(f"/api/data/{row['id']}/queries", json={"text": "please check"})
    count = bgh.get("/api/notifications/unread-count").json()["unread"]
    assert count >= 2
    rows = bgh.get("/api/notifications").json()
    first = rows[0]["id"]
    assert bgh.post(f"/api/notifications/{first}/read").json() == {"read": 1}
    assert bgh.get("/api/notifications/unread-count").json()["unread"] == count - 1
    rows = bgh.get("/api/notifications").json()
    assert rows[-1]["id"] == first and rows[-1]["read_at"], "unread first"
    assert all(n["kind"] == "form_locked" for n in bgh.get("/api/notifications", params={"kind": "form_locked"}).json())
    assert bgh.get("/api/notifications", params={"protocol_id": 999999}).json() == []
    # Someone else's notification is not found, and mark all clears the badge.
    assert dm.post(f"/api/notifications/{first}/read").status_code == 404
    bgh.post("/api/notifications/read-all")
    assert bgh.get("/api/notifications/unread-count").json()["unread"] == 0
