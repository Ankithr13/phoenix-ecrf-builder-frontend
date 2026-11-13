"""Built-in edit checks take their owner from the client's specification, and
EC-005 its wording. Checks on forms locked earlier were written with "system".

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

OWNERS = {"EC-001": "DM", "EC-002": "DM", "EC-003": "DM/Monitor", "EC-004": "DM/Clinical", "EC-005": "Site",
          "EC-006": "DM", "EC-007": "DM", "EC-008": "DM", "EC-009": "Safety/DM", "EC-010": "DM", "EC-012": "DM",
          "REQ": "DM", "FMT": "DM"}


def upgrade() -> None:
    conn = op.get_bind()
    for code, owner in OWNERS.items():
        conn.execute(sa.text("UPDATE edit_check SET owner = :owner WHERE origin = 'builtin' AND code = :code"),
                     {"owner": owner, "code": code})
    conn.execute(sa.text("UPDATE edit_check SET message = :m WHERE origin = 'builtin' AND code = 'EC-005'"),
                 {"m": "Enter visit date or document visit not performed."})


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE edit_check SET owner = 'system' WHERE origin = 'builtin'"))
