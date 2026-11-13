"""demo.sh rebuilds its database through scripts/build_demo_db.py, which tells
the story in scripts/demo_seed.py through the real API."""

import runpy
import sqlite3
from datetime import date
from pathlib import Path

from conftest import PASSWORD, fresh_client
from sqlalchemy import select

from ecrf import clock
from ecrf.config import config
from ecrf.storage import db
from ecrf.storage.models import Observation, Query, Subject, User

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_demo_db.py"
AS_OF = date(2026, 11, 12)


def test_demo_seed_covers_every_state(client):
    build = runpy.run_path(str(SCRIPT))
    seed = build["demo_seed"]
    pid = build["build"](fresh_client, PASSWORD, AS_OF)
    assert clock._fixed is None, "the seed hands the clock back"

    # check() raises on the first missing state; the asserts below say what it covers.
    summary = seed.check(fresh_client, PASSWORD, pid)
    with db.session() as s:
        codes = sorted(s.scalars(select(Subject.code).where(Subject.protocol_id == pid)))
        statuses = set(s.scalars(select(Observation.status).where(Observation.protocol_id == pid)))
        raised = sorted({q.raised_at.date() for q in s.scalars(select(Query))})
        assert len(s.scalars(select(User)).all()) == 10
    assert codes == [f"BGH-{n:03d}" for n in range(1, 11)] + [f"MRC-{n:03d}" for n in range(1, 7)]
    assert {"draft", "submitted", "approved"} <= statuses
    subjects = summary["subjects"]
    assert subjects["BGH-004"]["needs_signoff"] and subjects["BGH-005"]["needs_resign"]
    assert all(n > 0 for n in summary["queries"].values()), summary["queries"]
    assert all(n > 0 for n in summary["unread"].values()), summary["unread"]
    assert summary["read"]["dm@phoenix.demo"] == 3 and summary["read"]["crc@bgh.demo"] == 2
    assert summary["stats"] and all(x["status"] == "pass" for x in summary["stats"])
    # The story is spread over the weeks before as_of, for the Queries 360 trend.
    assert raised[0] < raised[-1] and (AS_OF - raised[0]).days <= seed.SPAN

    # The live walkthrough from the app guide still works, on a copy. The copy
    # is of a SQLite file, so a run against Postgres skips it.
    if config.database_url.startswith("sqlite"):
        steps = build["walkthrough_on_copy"](Path(config.database_url.removeprefix("sqlite:///")))
        assert steps == ["registered BGH-011", "BMI 84.4", "submitted, EC-006 raised", "query closed",
                         "approved", "signed", "blank eCRF PDF"]
        with db.session() as s:
            assert s.scalars(select(Subject).where(Subject.code == "BGH-011")).first() is None, "the copy took it"

    # Repeatable: the same as_of plans the same values.
    assert seed.plan(AS_OF) == seed.plan(AS_OF)


def test_demo_db_is_rebuilt_only_when_behind(tmp_path):
    build = runpy.run_path(str(SCRIPT))
    is_current = build["is_current"]
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
    assert is_current(stale) is False, "at the head, but built before the current story"
    build["story_file"](stale).write_text("an older story\n")
    assert is_current(stale) is False
    build["story_file"](stale).write_text(build["STORY"] + "\n")
    assert is_current(stale) is True
