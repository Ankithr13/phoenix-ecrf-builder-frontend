"""Set up a Postgres database (Supabase, Neon, Railway) for a hosted deployment.

    python scripts/load_postgres.py [--env-file PATH] [--accounts-only | --migrate-only] [--replace]

The target is DATABASE_URL, read from the environment or from --env-file.
By default it runs the migrations and then loads the demo story: the 16
synthetic patients from scripts/demo_seed.py. The story is built on a
temporary SQLite file first, through the real API, checked, and then copied
across row by row. Building it directly over the network would take thousands
of round trips. The copy is then checked by running the independent statistics
on both databases and comparing them.

    --accounts-only   migrations and the ten demo accounts, no patients
    --migrate-only    migrations only
    --replace         delete every row in the target first. Without it the
                      script refuses to touch a database that already has users.

Demo account passwords come from DEMO_PASSWORD (default demo1234). A hosted
deployment is reachable by anyone with the link, so set a private one.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--env-file", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--accounts-only", action="store_true")
    mode.add_argument("--migrate-only", action="store_true")
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args(argv)


ARGS = _arguments(sys.argv[1:]) if __name__ == "__main__" else None
if ARGS and ARGS.env_file:
    from dotenv import load_dotenv

    if not ARGS.env_file.exists():
        raise SystemExit(f"{ARGS.env_file} does not exist")
    load_dotenv(ARGS.env_file, override=True)

sys.path.insert(0, str(BACKEND))

from sqlalchemy import Integer, create_engine, func, select  # noqa: E402

from ecrf.config import config  # noqa: E402
from ecrf.storage import db, migrate  # noqa: E402
from ecrf.storage.models import Base, SapItem, User  # noqa: E402
from verification import expected_results as independent  # noqa: E402

# Sessions are signed with the build's SECRET_KEY and would never match the
# deployment's, so they are not copied. Everyone signs in afresh.
NOT_COPIED = {"session"}


def _target() -> str:
    url = config.database_url
    if not url.startswith("postgresql"):
        raise SystemExit("DATABASE_URL must be a Postgres URL (postgresql://...). "
                         "For a local SQLite demo database use midterm-assets/demo/demo.sh.")
    if "[YOUR-PASSWORD]" in url:
        raise SystemExit("DATABASE_URL still says [YOUR-PASSWORD]. Put the Supabase database password there.")
    return url


def _host(url: str) -> str:
    """The host only, so the password in the URL is never printed."""
    return url.split("@", 1)[-1].split("/", 1)[0]


def _empty_or_replace(replace: bool) -> None:
    """A database with no users holds only what the migrations inserted (the
    default sponsor organisation), which the copy brings back."""
    with db.session() as s:
        users = s.scalar(select(func.count()).select_from(User))
    if users and not replace:
        raise SystemExit(f"The target already has {users} users. Run again with --replace to delete "
                         "every row in it first, or point DATABASE_URL at an empty database.")
    with db._engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    if users:
        print("Deleted every row in the target.")


def _build_story(workdir: Path) -> Path:
    """The demo story on a temporary SQLite file, in a separate process so it
    has its own engine and never sees the target's DATABASE_URL."""
    source = workdir / "demo.db"
    env = os.environ | {
        "DATABASE_URL": f"sqlite:///{source}",
        "ECRF_UPLOAD_DIR": str(workdir / "uploads"),
        "ECRF_BACKEND": "mock",
        "ECRF_ENV": "dev",
        "DEMO_PASSWORD": config.demo_password,
    }
    print("Building the demo story on a temporary SQLite database (about a minute)...")
    r = subprocess.run([sys.executable, str(HERE / "build_demo_db.py")], env=env, cwd=BACKEND,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"Building the demo story failed:\n{r.stdout}{r.stderr}")
    return source


def _copy(source: Path) -> dict[str, int]:
    counts = {}
    src = create_engine(f"sqlite:///{source}")
    with src.connect() as a, db._engine.begin() as b:
        for table in Base.metadata.sorted_tables:
            if table.name in NOT_COPIED:
                continue
            rows = [dict(r._mapping) for r in a.execute(select(table))]
            for i in range(0, len(rows), 500):
                b.execute(table.insert(), rows[i:i + 500])
            counts[table.name] = len(rows)
        # Rows came in with their ids, so each id sequence must move past them.
        for table in Base.metadata.sorted_tables:
            pk = list(table.primary_key.columns)
            if len(pk) == 1 and isinstance(pk[0].type, Integer):
                b.exec_driver_sql(
                    f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', '{pk[0].name}'), "
                    f"COALESCE((SELECT MAX(\"{pk[0].name}\") FROM \"{table.name}\"), 0) + 1, false)")
    src.dispose()
    return counts


def _compare(source: Path, counts: dict[str, int]) -> int:
    """Same row counts, and the independent statistics agree on both."""
    with db._engine.connect() as conn:
        for name, n in counts.items():
            got = conn.exec_driver_sql(f'SELECT COUNT(*) FROM "{name}"').scalar()
            if got != n:
                raise SystemExit(f"{name}: copied {n} rows but the target has {got}")
    with db.session() as s:
        items = [(i.protocol_id, i.id, i.label) for i in s.scalars(select(SapItem))]
    for protocol_id, item_id, label in items:
        here = independent.item_results(f"sqlite:///{source}", protocol_id, item_id)
        there = independent.item_results(config.database_url, protocol_id, item_id)
        if here != there:
            raise SystemExit(f"Results differ after the copy for {label!r}")
    return len(items)


def main() -> int:
    args = ARGS or _arguments([])
    url = _target()
    print(f"Target: {_host(url)}")
    migrate.upgrade_head()
    print("Migrations applied.")
    if args.migrate_only:
        return 0
    _empty_or_replace(args.replace)
    if config.demo_password == "demo1234":
        print("WARNING: DEMO_PASSWORD is the default demo1234, which is written in the repository. "
              "Anyone with the link can sign in as any demo account.")
    if args.accounts_only:
        from ecrf.auth import demo

        with db.session() as s:
            users = demo.seed(s, password=config.demo_password)
        print(f"{len(users)} demo accounts created.")
        return 0
    with tempfile.TemporaryDirectory(prefix="ecrf-load-") as tmp:
        source = _build_story(Path(tmp))
        counts = _copy(source)
        checked = _compare(source, counts)
    print(f"Loaded {sum(counts.values())} rows into {len(counts)} tables; "
          f"{checked} results match the local build.")
    print("Demo accounts: the ten @phoenix.demo, @bgh.demo and @mrc.demo emails in docs/demo-data.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
