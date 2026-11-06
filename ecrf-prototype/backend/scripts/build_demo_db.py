"""Build the demo database from nothing, through the same API a person would use.

    DATABASE_URL=sqlite:////path/clean.db python scripts/build_demo_db.py
    python scripts/build_demo_db.py --current /path/clean.db

The first runs the migrations, creates the nine demo accounts, loads the bundled
sample with the mock extractor, confirms its visits, approves every field, locks
the form, assigns Boston General and Mercy, and seeds 20 synthetic subjects whose
values wait for approval. It never calls a paid model. The second exits 0 if that
database is at the code's migration head, and 1 if not.
"""

import os
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path

if __name__ == "__main__":
    os.environ["ECRF_BACKEND"] = "mock"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic.script import ScriptDirectory

from ecrf.auth import demo
from ecrf.storage import db, migrate
from ecrf.storage.models import Organisation

PASSWORD_NOTE = "password from DEMO_PASSWORD, default demo1234"


def is_current(path: Path) -> bool:
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
    return bool(row) and row[0] == head


def _ok(r, what: str):
    if r.status_code != 200:
        raise SystemExit(f"{what} failed: {r.status_code} {r.text[:300]}")
    return r.json()


def build(new_client: Callable, password: str) -> int:
    """Everything after the migrations. new_client() gives a client that has not
    signed in. Returns the protocol's id."""
    with db.session() as s:
        demo.seed(s, password=password)
        sites = {o.code: o.id for o in s.query(Organisation).filter(Organisation.code.in_(("BGH", "MRC")))}

    def signed_in(email: str):
        c = new_client()
        _ok(c.post("/api/auth/login", json={"email": email, "password": password}), f"login {email}")
        return c

    builder = signed_in("builder@phoenix.demo")
    pid = _ok(builder.post("/api/protocols/sample"), "load sample")["id"]
    visits = _ok(builder.post(f"/api/protocols/{pid}/extract/visits"), "find visits")["visits"]
    _ok(builder.put(f"/api/protocols/{pid}/visits", json={"visits": visits}), "confirm visits")
    _ok(builder.post(f"/api/protocols/{pid}/extract/fields"), "extract fields")
    forms = _ok(builder.get(f"/api/protocols/{pid}/draft"), "read draft")["draft"]["forms"]
    undecided = [{"visit": form["visit"], "name": f["name"], "status": "approved"}
                 for form in forms for f in form["fields"] if f["status"] != "approved"]
    _ok(builder.post(f"/api/protocols/{pid}/review", json={"changes": undecided}), "approve fields")

    dm = signed_in("dm@phoenix.demo")
    _ok(dm.post(f"/api/protocols/{pid}/lock"), "lock form")
    for org_id in sites.values():
        _ok(dm.post(f"/api/protocols/{pid}/sites", json={"site_org_id": org_id}), "assign site")
    _ok(dm.post(f"/api/data/seed/{pid}"), "seed subjects")
    return pid


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--current":
        return 0 if is_current(Path(sys.argv[2])) else 1
    if len(sys.argv) != 1:
        print(__doc__)
        return 2

    from fastapi.testclient import TestClient

    from ecrf.api.app import app
    from ecrf.config import config

    migrate.upgrade_head()
    with TestClient(app) as first:
        first.cookies.clear()
        pid = build(lambda: TestClient(app), config.demo_password)
    print(f"Demo database built: protocol {pid}, nine accounts, {PASSWORD_NOTE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
