"""The SAP matrix's Endpoint / Concept column. Existing rows start from their label.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sap_item") as b:
        b.add_column(sa.Column("endpoint_concept", sa.Text, nullable=False, server_default=""))
    op.get_bind().execute(sa.text("UPDATE sap_item SET endpoint_concept = label"))


def downgrade() -> None:
    with op.batch_alter_table("sap_item") as b:
        b.drop_column("endpoint_concept")
