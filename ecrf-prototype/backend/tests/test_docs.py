"""Sprint 3, stage 8: documents that must stay true to the code."""

import runpy
from pathlib import Path

from ecrf.auth.permissions import _MATRIX
from ecrf.checks.engine import TYPES

BACKEND = Path(__file__).resolve().parent.parent
DOCS = BACKEND.parent.parent / "docs"


def test_db_schema_doc_is_current():
    script = runpy.run_path(str(BACKEND / "scripts" / "db_schema.py"))
    assert (DOCS / "db-schema.md").read_text() == script["render"](), "run scripts/db_schema.py"


def test_roles_doc_lists_every_permission():
    text = (DOCS / "roles-and-permissions.md").read_text()
    for perm in _MATRIX:
        assert f"`{perm}`" in text, perm


def test_edit_checks_doc_lists_every_type():
    text = (DOCS / "edit-checks.md").read_text()
    for kind in TYPES:
        assert f"`{kind}`" in text, kind
    for n in range(1, 13):
        assert f"EC-{n:03d}" in text
