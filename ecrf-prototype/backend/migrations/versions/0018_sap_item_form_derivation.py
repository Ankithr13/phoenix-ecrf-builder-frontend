"""Store the eCRF form and the analysis derivation on each SAP row, filled in
from the chosen field and calculation when a result is added or edited.
Existing rows keep null, and the API works both out from the form as before.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sap_item") as b:
        b.add_column(sa.Column("form", sa.String(200), nullable=True))
        b.add_column(sa.Column("derivation", sa.Text, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sap_item") as b:
        b.drop_column("derivation")
        b.drop_column("form")
