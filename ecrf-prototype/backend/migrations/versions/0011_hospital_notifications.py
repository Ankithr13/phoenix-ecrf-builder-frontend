import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hospital_submission",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
        sa.Column("site_org_id", sa.Integer, sa.ForeignKey("organisation.id"), nullable=False),
        sa.Column("ecrf_version_id", sa.Integer, sa.ForeignKey("ecrf_version.id"), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("patient_count", sa.Integer, nullable=False),
        sa.Column("submitted_by", sa.String(200), nullable=False),
        sa.Column("submitted_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("protocol_id", "site_org_id", "snapshot_hash", name="uq_hospital_submission_snapshot"),
    )
    op.create_table(
        "notification",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organisation.id"), nullable=False),
        sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
        sa.Column("site_org_id", sa.Integer, sa.ForeignKey("organisation.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("event_key", sa.String(100), nullable=False, unique=True),
        sa.Column("query_id", sa.Integer, sa.ForeignKey("query.id"), nullable=True),
        sa.Column("submission_id", sa.Integer, sa.ForeignKey("hospital_submission.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_notification_org_id", "notification", ["org_id"])
    op.create_table(
        "notification_read",
        sa.Column("notification_id", sa.Integer, sa.ForeignKey("notification.id"), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), primary_key=True),
        sa.Column("read_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_read")
    op.drop_index("ix_notification_org_id", table_name="notification")
    op.drop_table("notification")
    op.drop_table("hospital_submission")
