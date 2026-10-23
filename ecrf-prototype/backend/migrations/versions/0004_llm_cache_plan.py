"""LLM call cache and the stored extraction plan.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_call",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("request_json", sa.JSON, nullable=False),
        sa.Column("response_text", sa.Text, nullable=False),
        sa.Column("usage_json", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("hits", sa.Integer, nullable=False, server_default="0"),
    )
    with op.batch_alter_table("protocol") as b:
        b.add_column(sa.Column("extraction_plan", sa.JSON, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("protocol") as b:
        b.drop_column("extraction_plan")
    op.drop_table("llm_call")
