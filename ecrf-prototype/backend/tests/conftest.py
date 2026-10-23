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
from fastapi.testclient import TestClient  # noqa: E402

from ecrf.api.app import app  # noqa: E402
from ecrf.auth import demo, sessions  # noqa: E402
from ecrf.storage import db, migrate  # noqa: E402
from ecrf.storage.models import Base  # noqa: E402

PASSWORD = "demo1234"
BUILDER, APPROVER, BGH, MRC = ("builder@phoenix.demo", "approver@phoenix.demo",
                               "staff@bgh.demo", "staff@mrc.demo")


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
    sessions._failures.clear()


@pytest.fixture
def demo_accounts():
    with db.session() as s:
        demo.seed(s, PASSWORD)
    return {"builder": BUILDER, "approver": APPROVER, "bgh": BGH, "mrc": MRC}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def fresh_client() -> TestClient:
    """A second browser, for tests that need two users at once."""
    return TestClient(app)


def login(c: TestClient, email: str, password: str = PASSWORD) -> dict:
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()
