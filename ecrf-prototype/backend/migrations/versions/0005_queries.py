"""Queries on entered values.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "query",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("observation_id", sa.Integer, sa.ForeignKey("observation.id"), nullable=False),
        sa.Column("raised_by", sa.String(100), nullable=False),
        sa.Column("raised_at", sa.DateTime, nullable=False),
        sa.Column("text", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("answer_text", sa.String(1000), nullable=True),
        sa.Column("answered_by", sa.String(100), nullable=True),
        sa.Column("answered_at", sa.DateTime, nullable=True),
        sa.Column("closed_by", sa.String(100), nullable=True),
        sa.Column("closed_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("query")
