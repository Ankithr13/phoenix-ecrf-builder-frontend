"""Fixes from the November audit.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-05

Uploads are stored under a generated name, so the protocol keeps the
original filename and gains the stored one. Patients lose their initials.
The value status "entered" becomes "submitted".
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("protocol") as b:
        b.add_column(sa.Column("stored_filename", sa.String(300), nullable=True))
    with op.batch_alter_table("subject") as b:
        b.drop_column("initials")
    op.execute("UPDATE observation SET status = 'submitted' WHERE status = 'entered'")
    with op.batch_alter_table("observation") as b:
        b.alter_column("status", existing_type=sa.String(20), server_default="submitted")


def downgrade() -> None:
    with op.batch_alter_table("observation") as b:
        b.alter_column("status", existing_type=sa.String(20), server_default="entered")
    op.execute("UPDATE observation SET status = 'entered' WHERE status = 'submitted'")
    with op.batch_alter_table("subject") as b:
        b.add_column(sa.Column("initials", sa.String(5), nullable=True))
    with op.batch_alter_table("protocol") as b:
        b.drop_column("stored_filename")
