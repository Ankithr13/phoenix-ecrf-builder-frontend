"""Edit checks, the draft status, and how a field was completed.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-05

"queried" stops being a status. A value keeps its status and its open queries
are counted alongside. An old queried row that had been approved returns to
approved, because the query is still there to block anything further.
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "edit_check",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("form", sa.String(200), nullable=True),
        sa.Column("field_ids", sa.JSON, nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("logic", sa.JSON, nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("owner", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("origin", sa.String(10), nullable=False),
        sa.Column("form_version", sa.Integer, nullable=False),
    )
    with op.batch_alter_table("observation") as b:
        b.add_column(sa.Column("completion_status", sa.String(20), nullable=False, server_default="value"))
        b.add_column(sa.Column("completion_reason", sa.String(500), nullable=True))
        b.alter_column("status", existing_type=sa.String(20), server_default="draft")
    op.execute("UPDATE observation SET status = 'approved' WHERE status = 'queried' AND approved_by IS NOT NULL")
    op.execute("UPDATE observation SET status = 'submitted' WHERE status = 'queried'")
    with op.batch_alter_table("query") as b:
        b.add_column(sa.Column("check_code", sa.String(20), nullable=True))
        b.add_column(sa.Column("check_key", sa.String(40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("query") as b:
        b.drop_column("check_key")
        b.drop_column("check_code")
    with op.batch_alter_table("observation") as b:
        b.alter_column("status", existing_type=sa.String(20), server_default="submitted")
        b.drop_column("completion_reason")
        b.drop_column("completion_status")
    op.drop_table("edit_check")
