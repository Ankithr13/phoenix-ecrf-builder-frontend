"""Every test runs against a temporary database with the mock backend.

The environment is set before anything from ecrf is imported, because
ecrf.config reads it once at import time and the engine is built from it.
"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="ecrf-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["ECRF_BACKEND"] = "mock"
os.environ["ECRF_CONTEXT"] = "auto"
os.environ["ECRF_UPLOAD_DIR"] = f"{_TMP}/uploads"

import pytest  # noqa: E402

from ecrf.storage import db, migrate  # noqa: E402
from ecrf.storage.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    migrate.upgrade_head()


@pytest.fixture(autouse=True)
def clean_tables(schema):
    """Each test starts from empty tables but keeps the migrated schema."""
    yield
    with db._engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
