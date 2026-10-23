"""Baseline: the three tables the prototype shipped with.

Revision ID: 0001
Revises:
Create Date: 2026-10-22

Every table is created only if it does not already exist. Databases built
by the old create_all() path therefore pass through this migration
untouched and simply get stamped, while an empty file gets the full schema.
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _missing(name: str) -> bool:
    return not sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _missing("protocol"):
        op.create_table(
            "protocol",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("filename", sa.String(300), nullable=False),
            sa.Column("text_hash", sa.String(64), nullable=False),
            sa.Column("normalised", sa.Text, nullable=False),
            sa.Column("sections", sa.JSON, nullable=False),
            sa.Column("pages", sa.Integer, nullable=False),
            sa.Column("tokens_estimate", sa.Integer, nullable=False),
            sa.Column("uploaded_by", sa.String(100), nullable=False),
            sa.Column("uploaded_at", sa.DateTime, nullable=False),
        )
    if _missing("ecrf_version"):
        op.create_table(
            "ecrf_version",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
            sa.Column("protocol_hash", sa.String(64), nullable=False),
            sa.Column("version", sa.Integer, nullable=False),
            sa.Column("content", sa.JSON, nullable=False),
            sa.Column("created_by", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.UniqueConstraint("protocol_id", "version", name="uq_ecrf_version_protocol_version"),
        )
    if _missing("observation"):
        op.create_table(
            "observation",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
            sa.Column("subject_id", sa.String(50), nullable=False),
            sa.Column("visit", sa.String(100), nullable=False),
            sa.Column("field_name", sa.String(200), nullable=False),
            sa.Column("repeat_num", sa.Integer, nullable=False),
            sa.Column("value_num", sa.Float, nullable=True),
            sa.Column("value_text", sa.String(500), nullable=True),
            sa.Column("synthetic", sa.Boolean, nullable=False),
            sa.Column("entered_by", sa.String(100), nullable=False),
            sa.Column("entered_at", sa.DateTime, nullable=False),
            sa.UniqueConstraint("protocol_id", "subject_id", "visit", "field_name", "repeat_num",
                                name="uq_observation_slot"),
        )


def downgrade() -> None:
    op.drop_table("observation")
    op.drop_table("ecrf_version")
    op.drop_table("protocol")
