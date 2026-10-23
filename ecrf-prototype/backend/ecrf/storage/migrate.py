"""Run and check Alembic migrations from Python.

The schema is no longer created by create_all() at startup. run.sh applies
migrations before starting the server, the test fixture applies them to a
temporary database, and the app refuses to start on a database that is
behind, because a missing column surfaces as a bare 500 otherwise."""

from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from ecrf.config import config

BACKEND = Path(__file__).resolve().parents[2]


def alembic_config() -> AlembicConfig:
    cfg = AlembicConfig(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", config.database_url)
    return cfg


def upgrade_head() -> None:
    command.upgrade(alembic_config(), "head")


def schema_status(engine: Engine) -> tuple[str | None, str]:
    """(applied revision or None, head revision)."""
    head = ScriptDirectory.from_config(alembic_config()).get_current_head() or ""
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    return current, head


def assert_up_to_date(engine: Engine) -> None:
    current, head = schema_status(engine)
    if current != head:
        raise RuntimeError(
            f"database schema is at revision {current or 'none'} but the code expects "
            f"{head}. Run `alembic upgrade head` in ecrf-prototype/backend (run.sh does "
            f"this automatically)."
        )
