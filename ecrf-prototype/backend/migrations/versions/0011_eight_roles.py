"""Eight roles, the access record, monitor sites, and the approval chain switches.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-05

The old sponsor role becomes data_manager and site_staff becomes
site_coordinator, the closest match to what each could do.
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user") as b:
        b.add_column(sa.Column("must_change_password", sa.Boolean, nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("created_by", sa.String(100), nullable=True))
    op.execute("""UPDATE "user" SET role = 'data_manager' WHERE role = 'sponsor'""")
    op.execute("""UPDATE "user" SET role = 'site_coordinator' WHERE role = 'site_staff'""")
    with op.batch_alter_table("protocol") as b:
        b.add_column(sa.Column("monitor_review_required", sa.Boolean, nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("investigator_signature_required", sa.Boolean, nullable=False, server_default=sa.true()))
    op.create_table(
        "monitor_site",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False),
        sa.Column("site_org_id", sa.Integer, sa.ForeignKey("organisation.id"), nullable=False),
        sa.Column("assigned_by", sa.String(100), nullable=False),
        sa.Column("assigned_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("user_id", "site_org_id", name="uq_monitor_site"),
    )
    op.create_table(
        "user_access_event",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("by", sa.String(100), nullable=False),
        sa.Column("at", sa.DateTime, nullable=False),
        sa.Column("detail", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_access_event")
    op.drop_table("monitor_site")
    with op.batch_alter_table("protocol") as b:
        b.drop_column("investigator_signature_required")
        b.drop_column("monitor_review_required")
    op.execute("""UPDATE "user" SET role = 'sponsor' WHERE role IN ('admin', 'builder', 'data_manager', 'monitor', 'read_only')""")
    op.execute("""UPDATE "user" SET role = 'site_staff' WHERE role IN ('investigator', 'site_coordinator', 'site_data_entry')""")
    with op.batch_alter_table("user") as b:
        b.drop_column("created_by")
        b.drop_column("must_change_password")
