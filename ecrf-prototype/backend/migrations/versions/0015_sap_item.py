"""The statistical analysis plan's rows.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-05
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sap_item",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("field_id", sa.String(32), nullable=False),
        sa.Column("baseline_visit_id", sa.String(100), nullable=True),
        sa.Column("analysis_visit_id", sa.String(100), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("responder_rule", sa.JSON, nullable=True),
        sa.Column("method", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sap_item")
