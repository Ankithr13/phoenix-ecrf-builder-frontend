"""Field comments and the field-level audit trail for form edits.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-05
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "field_comment",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("field_id", sa.String(32), nullable=False),
        sa.Column("author", sa.String(100), nullable=False),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("resolved_by", sa.String(100), nullable=True),
    )
    op.create_table(
        "form_field_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("field_id", sa.String(32), nullable=True),
        sa.Column("attribute", sa.String(40), nullable=False),
        sa.Column("old_value", sa.String(1000), nullable=True),
        sa.Column("new_value", sa.String(1000), nullable=True),
        sa.Column("by", sa.String(100), nullable=False),
        sa.Column("at", sa.DateTime, nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("form_field_history")
    op.drop_table("field_comment")
