"""Sprint 3 fixes: demo.sh rebuilds its database through this script."""

import runpy
import sqlite3
from pathlib import Path

from conftest import APPROVER, PASSWORD, fresh_client, login
from sqlalchemy import select

from ecrf.storage import db
from ecrf.storage.models import Observation, Subject, User

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_demo_db.py"


def test_demo_seed_builds_a_locked_protocol_with_subjects(client):
    pid = runpy.run_path(str(SCRIPT))["build"](fresh_client, PASSWORD)
    with db.session() as s:
        assert len(s.scalars(select(User)).all()) == 9
        subjects = s.scalars(select(Subject).where(Subject.protocol_id == pid)).all()
        rows = s.scalars(select(Observation).where(Observation.protocol_id == pid)).all()
        assert len(subjects) == 20
        assert rows and {o.status for o in rows} == {"submitted"}

    login(client, APPROVER)
    draft = client.get(f"/api/protocols/{pid}/draft").json()
    assert draft["state"] == "locked"
    assert all(f["status"] == "approved" for form in draft["draft"]["forms"] for f in form["fields"])
    assert (client.get(f"/api/protocols/{pid}/visits").json()["confirmed"]) is True
    assert {x["code"] for x in client.get(f"/api/protocols/{pid}/sites").json() if x["assigned"]} == {"BGH", "MRC"}


def test_demo_db_is_rebuilt_only_when_behind(tmp_path):
    is_current = runpy.run_path(str(SCRIPT))["is_current"]
    assert is_current(tmp_path / "missing.db") is False

    stale = tmp_path / "stale.db"
    con = sqlite3.connect(stale)
    con.execute("CREATE TABLE alembic_version (version_num TEXT)")
    con.execute("INSERT INTO alembic_version VALUES ('0009')")
    con.commit()
    con.close()
    assert is_current(stale) is False

    with db._engine.connect() as conn:
        head = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
    con = sqlite3.connect(stale)
    con.execute("UPDATE alembic_version SET version_num = ?", (head,))
    con.commit()
    con.close()
    assert is_current(stale) is True
