"""The admin panel, the access record, first login, and the role migration."""

import sqlite3

from alembic import command
from alembic.config import Config as AlembicConfig
from conftest import ADMIN, APPROVER, BGH, BUILDER, PASSWORD, fresh_client, login
from sqlalchemy import select
from test_lock_sites_data import _org_id, sponsor_draft

from ecrf.storage import db, migrate
from ecrf.storage.models import MonitorSite, User, UserAccessEvent


def _admin(client):
    login(client, ADMIN)
    return client


def _actions(email: str) -> list[str]:
    with db.session() as s:
        u = s.scalars(select(User).where(User.email == email)).first()
        return [e.action for e in s.scalars(select(UserAccessEvent).where(UserAccessEvent.user_id == u.id).order_by(UserAccessEvent.id))]


def test_old_roles_migrate_to_new_roles(tmp_path):
    path = tmp_path / "old.db"
    cfg = AlembicConfig(str(migrate.BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(migrate.BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "0010")
    con = sqlite3.connect(path)
    con.execute("INSERT INTO organisation (id, name, type, code, created_at) VALUES (900,'B','site','BGH','2026-01-01')")
    con.execute("""INSERT INTO "user" (email, name, password_hash, org_id, role, is_active, created_at)
                   VALUES ('s@x','S','h',(SELECT id FROM organisation WHERE code='PHX'),'sponsor',1,'2026-01-01'),
                          ('t@x','T','h',900,'site_staff',1,'2026-01-01')""")
    con.commit()
    con.close()
    command.upgrade(cfg, "head")
    con = sqlite3.connect(path)
    roles = dict(con.execute('SELECT email, role FROM "user"'))
    changed = con.execute('SELECT must_change_password FROM "user"').fetchall()
    con.close()
    assert roles == {"s@x": "data_manager", "t@x": "site_coordinator"}
    assert all(row[0] == 0 for row in changed), "existing people are not forced to change password"


def test_admin_creates_user_and_access_event_is_written(client, demo_accounts):
    _admin(client)
    r = client.post("/api/admin/users", json={"email": "New.Person@bgh.demo", "name": "New Person",
                                              "org_id": _org_id("BGH"), "role": "site_data_entry"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "new.person@bgh.demo" and r.json()["user"]["must_change_password"] is True
    assert r.json()["temporary_password"]
    assert "temporary_password" not in client.get("/api/admin/users").text
    assert _actions("new.person@bgh.demo") == ["created"]
    log = client.get("/api/admin/access-log").json()
    assert log[0]["user"] == "new.person@bgh.demo" and log[0]["by"] == ADMIN and "site_data_entry" in log[0]["detail"]

    # Roles belong to the side of the organisation.
    assert client.post("/api/admin/users", json={"email": "x@bgh.demo", "name": "X", "org_id": _org_id("BGH"),
                                                 "role": "data_manager"}).status_code == 422
    assert client.post("/api/admin/users", json={"email": "new.person@bgh.demo", "name": "X", "org_id": _org_id("BGH"),
                                                 "role": "site_data_entry"}).status_code == 409
    # Filters.
    rows = client.get("/api/admin/users", params={"org_id": _org_id("BGH"), "role": "site_data_entry"}).json()
    assert {u["email"] for u in rows} == {"entry@bgh.demo", "new.person@bgh.demo"}


def test_admin_edits_role_and_monitor_sites(client, demo_accounts):
    _admin(client)
    users = {u["email"]: u for u in client.get("/api/admin/users").json()}
    cra = users["cra@phoenix.demo"]
    assert cra["monitor_site_ids"] == [_org_id("BGH")]
    r = client.patch(f"/api/admin/users/{cra['id']}", json={"monitor_site_ids": [_org_id("BGH"), _org_id("MRC")]})
    assert sorted(r.json()["monitor_site_ids"]) == sorted([_org_id("BGH"), _org_id("MRC")])
    assert "site_assigned" in _actions("cra@phoenix.demo")

    r = client.patch(f"/api/admin/users/{cra['id']}", json={"role": "read_only"})
    assert r.json()["role"] == "read_only" and r.json()["monitor_site_ids"] == []
    assert "role_changed" in _actions("cra@phoenix.demo")
    with db.session() as s:
        assert s.scalars(select(MonitorSite)).first() is None
    assert client.patch(f"/api/admin/users/{users[BGH]['id']}", json={"role": "builder"}).status_code == 422
    assert client.patch(f"/api/admin/users/{users[ADMIN]['id']}", json={"role": "builder"}).status_code == 409


def test_deactivated_user_cannot_log_in(client, demo_accounts):
    _admin(client)
    uid = next(u["id"] for u in client.get("/api/admin/users").json() if u["email"] == BUILDER)
    live = fresh_client()
    with live:
        login(live, BUILDER)
        assert client.post(f"/api/admin/users/{uid}/deactivate").json()["is_active"] is False
        assert live.get("/api/protocols").status_code == 401, "a live session ends too"
        assert live.post("/api/auth/login", json={"email": BUILDER, "password": PASSWORD}).status_code == 401
        assert client.post(f"/api/admin/users/{uid}/reactivate").json()["is_active"] is True
        login(live, BUILDER)
    assert _actions(BUILDER) == ["deactivated", "reactivated"]
    me = next(u["id"] for u in client.get("/api/admin/users").json() if u["email"] == ADMIN)
    assert client.post(f"/api/admin/users/{me}/deactivate").status_code == 409, "no locking yourself out"
    # A reset signs you out, so on your own account you'd never see the password.
    assert client.post(f"/api/admin/users/{me}/reset-password").status_code == 409
    assert client.get("/api/auth/me").status_code == 200, "still signed in"
    assert "password_reset" not in _actions(ADMIN)


def test_must_change_password_blocks_other_routes(client, demo_accounts):
    _admin(client)
    uid = next(u["id"] for u in client.get("/api/admin/users").json() if u["email"] == APPROVER)
    temporary = client.post(f"/api/admin/users/{uid}/reset-password").json()["temporary_password"]
    assert _actions(APPROVER) == ["password_reset"]

    c = fresh_client()
    with c:
        me = login(c, APPROVER, temporary)
        assert me["must_change_password"] is True
        assert c.get("/api/auth/me").status_code == 200
        r = c.get("/api/protocols")
        assert r.status_code == 403 and r.json()["detail"]["code"] == "must_change_password"
        bad = {"current_password": "wrong", "new_password": "a-new-password"}
        assert c.post("/api/auth/change-password", json=bad).status_code == 403
        short = {"current_password": temporary, "new_password": "short"}
        assert c.post("/api/auth/change-password", json=short).status_code == 422
        good = {"current_password": temporary, "new_password": "a-new-password"}
        assert c.post("/api/auth/change-password", json=good).json()["must_change_password"] is False
        assert c.get("/api/protocols").status_code == 200
    assert _actions(APPROVER)[-1] == "password_changed"


def test_approval_chain_switches(client, demo_accounts):
    pid = sponsor_draft()
    _admin(client)
    row = next(p for p in client.get("/api/admin/chain").json() if p["id"] == pid)
    assert row["monitor_review_required"] is False and row["investigator_signature_required"] is True
    r = client.put(f"/api/admin/chain/{pid}", json={"monitor_review_required": True})
    assert r.json()["monitor_review_required"] is True and r.json()["investigator_signature_required"] is True
    assert client.get("/api/admin/access-log").json()[0]["action"] == "chain_configured"
    assert client.put("/api/admin/chain/999999", json={}).status_code == 404
    dm = fresh_client()
    with dm:
        login(dm, APPROVER)
        assert dm.put(f"/api/admin/chain/{pid}", json={"monitor_review_required": False}).status_code == 403
