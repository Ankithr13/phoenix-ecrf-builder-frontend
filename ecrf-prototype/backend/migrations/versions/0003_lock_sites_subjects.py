"""Form lock, site assignment, subjects, data approval and history.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "protocol_site",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
        sa.Column("site_org_id", sa.Integer, sa.ForeignKey("organisation.id"), nullable=False),
        sa.Column("assigned_by", sa.String(100), nullable=False),
        sa.Column("assigned_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("protocol_id", "site_org_id", name="uq_protocol_site"),
    )
    op.create_table(
        "subject",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
        sa.Column("site_org_id", sa.Integer, sa.ForeignKey("organisation.id"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("protocol_id", "code", name="uq_subject_code"),
    )
    with op.batch_alter_table("ecrf_version") as b:
        b.add_column(sa.Column("state", sa.String(20), nullable=False, server_default="draft"))
        b.add_column(sa.Column("locked_by", sa.String(100), nullable=True))
        b.add_column(sa.Column("locked_at", sa.DateTime, nullable=True))
    with op.batch_alter_table("observation") as b:
        b.add_column(sa.Column("subject_ref", sa.Integer, nullable=True))
        b.add_column(sa.Column("ecrf_version_id", sa.Integer, nullable=True))
        b.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="entered"))
        b.add_column(sa.Column("approved_by", sa.String(100), nullable=True))
        b.add_column(sa.Column("approved_at", sa.DateTime, nullable=True))
        b.add_column(sa.Column("updated_at", sa.DateTime, nullable=True))
        b.create_foreign_key("fk_observation_subject_ref_subject", "subject", ["subject_ref"], ["id"])
        b.create_foreign_key("fk_observation_ecrf_version_id", "ecrf_version", ["ecrf_version_id"], ["id"])
    op.create_table(
        "observation_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("observation_id", sa.Integer, sa.ForeignKey("observation.id"), nullable=False),
        sa.Column("old_value", sa.String(500), nullable=True),
        sa.Column("new_value", sa.String(500), nullable=True),
        sa.Column("changed_by", sa.String(100), nullable=False),
        sa.Column("changed_at", sa.DateTime, nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("observation_history")
    with op.batch_alter_table("observation") as b:
        b.drop_constraint("fk_observation_ecrf_version_id", type_="foreignkey")
        b.drop_constraint("fk_observation_subject_ref_subject", type_="foreignkey")
        for col in ("updated_at", "approved_at", "approved_by", "status", "ecrf_version_id", "subject_ref"):
            b.drop_column(col)
    with op.batch_alter_table("ecrf_version") as b:
        for col in ("locked_at", "locked_by", "state"):
            b.drop_column(col)
    op.drop_table("subject")
    op.drop_table("protocol_site")
