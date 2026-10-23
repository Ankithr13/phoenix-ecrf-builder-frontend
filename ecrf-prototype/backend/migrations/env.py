"""Alembic environment. The target database comes from ecrf.config, so the
same DATABASE_URL that drives the app drives the migrations. SQLite cannot
ALTER most things in place, so batch mode is on: Alembic rebuilds the table
behind the scenes when a migration changes a column."""

from alembic import context
from sqlalchemy import create_engine, pool

from ecrf.config import config as ecrf_config
from ecrf.storage.models import Base

alembic_cfg = context.config
target_metadata = Base.metadata


def _url() -> str:
    return alembic_cfg.get_main_option("sqlalchemy.url") or ecrf_config.database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata,
                      literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
