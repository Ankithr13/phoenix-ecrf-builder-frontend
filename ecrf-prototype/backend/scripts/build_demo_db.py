"""Build the demo database from nothing, through the same API a person would use.

    DATABASE_URL=sqlite:////path/clean.db python scripts/build_demo_db.py [--as-of YYYY-MM-DD]
    python scripts/build_demo_db.py --current /path/clean.db

The first runs the migrations, creates the ten demo accounts, and tells the
story in scripts/demo_seed.py: the bundled sample loaded with the mock
extractor and locked, Boston General and Mercy assigned, and 16 synthetic
patients whose visits show every status, query state and notification type,
spread over the 28 days before --as-of (default today). It then checks every
state is there, runs the live walkthrough from the app guide on a copy, and
fails loudly if anything is missing. It never calls a paid model.

The second exits 0 if that database is at the code's migration head and holds
the current story, and 1 if not.
"""

import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path

if __name__ == "__main__":
    os.environ["ECRF_BACKEND"] = "mock"

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import demo_seed  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

from ecrf import clock  # noqa: E402
from ecrf.auth import demo  # noqa: E402
from ecrf.storage import db, migrate  # noqa: E402
from ecrf.storage.models import Protocol  # noqa: E402

PASSWORD_NOTE = "password from DEMO_PASSWORD, default demo1234"
# Change this when the story changes, so demo.sh rebuilds a database that is
# at the schema head but holds an older story.
STORY = "16 patients, 2026-11-12"


def story_file(path: Path) -> Path:
    return path.with_name(path.name + ".story")


def is_current(path: Path) -> bool:
    import sqlite3

    if not path.exists():
        return False
    con = sqlite3.connect(path)
    try:
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error:
        return False
    finally:
        con.close()
    head = ScriptDirectory.from_config(migrate.alembic_config()).get_current_head()
    marker = story_file(path)
    return bool(row) and row[0] == head and marker.exists() and marker.read_text().strip() == STORY


def build(new_client: Callable, password: str, as_of: date | None = None) -> int:
    """Everything after the migrations. new_client() gives a client that has not
    signed in. Returns the protocol's id."""
    as_of = as_of or clock.today()
    try:
        clock.set_to(datetime.combine(as_of - timedelta(days=demo_seed.SPAN + 1), time(7, 0)))
        with db.session() as s:
            demo.seed(s, password=password)
    finally:
        clock.set_to(None)
    return demo_seed.seed(new_client, password, as_of)["protocol_id"]


def _sqlite_path(url: str) -> Path:
    if not url.startswith("sqlite:///"):
        raise SystemExit("the demo database is SQLite only")
    return Path(url.removeprefix("sqlite:///"))


def walkthrough_on_copy(database: Path) -> list[str]:
    """Run the app guide's live walkthrough against a copy, in a separate
    process so it has its own engine. The seeded database is not touched."""
    with tempfile.TemporaryDirectory(prefix="ecrf-walkthrough-") as tmp:
        copy = Path(tmp) / "walkthrough.db"
        demo_seed.copy_database(str(database), str(copy))
        env = os.environ | {"DATABASE_URL": f"sqlite:///{copy}", "ECRF_UPLOAD_DIR": str(Path(tmp) / "uploads"),
                            "ECRF_BACKEND": "mock"}
        r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--walkthrough"], env=env,
                           capture_output=True, text=True, cwd=HERE.parent)
    if r.returncode != 0:
        raise SystemExit(f"The live walkthrough failed on a copy of the demo database:\n{r.stdout}{r.stderr}")
    return [line.removeprefix("ok: ") for line in r.stdout.splitlines() if line.startswith("ok: ")]


def _report(summary: dict, steps: list[str]) -> str:
    out = [f"Unread notifications: {summary['unread']}", f"Queries: {summary['queries']}", "Results:"]
    for x in summary["stats"]:
        out.append(f"  {x['item_label']} / {x['label']}: {x['status'].upper()} {x['app']}")
    out.append("Live walkthrough on a copy: " + ", ".join(steps))
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--current":
        return 0 if is_current(Path(argv[1])) else 1

    from fastapi.testclient import TestClient

    from ecrf.api.app import app
    from ecrf.config import config

    if argv == ["--walkthrough"]:
        with TestClient(app), db.session() as s:
            pid = s.query(Protocol).filter(Protocol.name.like("PHX-401-201%")).one().id
        for step in demo_seed.walkthrough(lambda: TestClient(app), config.demo_password, pid):
            print(f"ok: {step}")
        return 0

    as_of = None
    if len(argv) == 2 and argv[0] == "--as-of":
        as_of = date.fromisoformat(argv[1])
    elif argv:
        print(__doc__)
        return 2

    database = _sqlite_path(config.database_url)
    migrate.upgrade_head()
    with TestClient(app) as first:
        first.cookies.clear()
        pid = build(lambda: TestClient(app), config.demo_password, as_of)
        summary = demo_seed.check(lambda: TestClient(app), config.demo_password, pid)
    steps = walkthrough_on_copy(database)
    story_file(database).write_text(STORY + "\n")
    print(f"Demo database built: protocol {pid}, ten accounts, 16 patients, {PASSWORD_NOTE}.")
    print(_report(summary, steps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
