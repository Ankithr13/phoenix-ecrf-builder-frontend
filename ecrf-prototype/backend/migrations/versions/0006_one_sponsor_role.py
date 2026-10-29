"""One sponsor role instead of builder and approver.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-29

The two sponsor roles are merged into "sponsor" and the two demo accounts
are renamed so their addresses no longer imply different powers. The
audit columns that store an email are rewritten too, so history still
points at a real account.
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

RENAMES = {
    "builder@phoenix.demo": "dana@phoenix.demo",
    "approver@phoenix.demo": "alex@phoenix.demo",
}
EMAIL_COLUMNS = [
    ("user", "email"), ("protocol", "uploaded_by"), ("ecrf_version", "created_by"),
    ("ecrf_version", "locked_by"), ("protocol_site", "assigned_by"), ("subject", "created_by"),
    ("observation", "entered_by"), ("observation", "approved_by"),
    ("observation_history", "changed_by"), ("query", "raised_by"), ("query", "answered_by"),
    ("query", "closed_by"),
]


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE \"user\" SET role='sponsor' WHERE role IN ('builder', 'approver')"))
    for email, name in (("dana@phoenix.demo", "Dana Patel"), ("alex@phoenix.demo", "Alex Morgan")):
        conn.execute(sa.text("UPDATE \"user\" SET name=:name WHERE email=:old OR email=:new"),
                     {"name": name, "old": next(k for k, v in RENAMES.items() if v == email), "new": email})
    for old, new in RENAMES.items():
        for table, col in EMAIL_COLUMNS:
            conn.execute(sa.text(f"UPDATE \"{table}\" SET {col}=:new WHERE {col}=:old"),
                         {"new": new, "old": old})


def downgrade() -> None:
    conn = op.get_bind()
    for new, old in ((v, k) for k, v in RENAMES.items()):
        for table, col in EMAIL_COLUMNS:
            conn.execute(sa.text(f"UPDATE \"{table}\" SET {col}=:old WHERE {col}=:new"),
                         {"new": new, "old": old})
    conn.execute(sa.text("UPDATE \"user\" SET role='sponsor' WHERE role='sponsor'"))
