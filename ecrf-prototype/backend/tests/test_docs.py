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


COMPLETION_HEADINGS = ["1. Purpose", "2. Core Data Entry Expectations", "3. General Field Completion Rules",
                       "4. Form-by-Form Guide", "5. Queries", "6. Investigator Review and Sign-off",
                       "7. Pre-Lock Site Checklist", "8. Training Acknowledgment"]


def test_completion_guide_follows_the_client_template():
    text = (DOCS / "ecrf-completion-guidelines.md").read_text()
    positions = [text.index(f"## {h}\n") for h in COMPLETION_HEADINGS]
    assert positions == sorted(positions), "the client's order"
    assert "Draft for Phoenix to edit" in text
    for label in ("Protocol:", "Version:", "Effective Date:", "Prepared by:", "EDC System:", "Approved by:"):
        assert label in text
    for row in ("Dates", "Times", "Numeric values", "Text fields", "Yes/No fields", "Not Done / Not Applicable", "Unknown", "Corrections"):
        assert f"| {row} |" in text
    for row in ("Subject Identification", "Informed Consent", "Demographics", "Eligibility", "Visit Forms",
                "Medical History", "Concomitant Medications", "Adverse Events", "Study Completion"):
        assert f"| {row} |" in text
    section_6 = text[positions[5]:positions[6]]
    assert "signature" not in section_6.lower()
    assert text[positions[6]:positions[7]].count("- [ ]") == 7
