"""Queries can be raised by either side.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-29

Records which organisation type raised a query; every existing query was
raised by a sponsor.
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("query") as b:
        b.add_column(sa.Column("raised_by_org", sa.String(20), nullable=False, server_default="sponsor"))


def downgrade() -> None:
    with op.batch_alter_table("query") as b:
        b.drop_column("raised_by_org")
