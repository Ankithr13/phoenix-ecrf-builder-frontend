"""Query lifecycle, monitor review, investigator sign-off, study lock, notifications.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-05

Existing query statuses, open, answered and closed, carry over unchanged.
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("query") as b:
        b.add_column(sa.Column("raised_by_role", sa.String(30), nullable=True))
        b.add_column(sa.Column("close_reason", sa.String(500), nullable=True))
        b.add_column(sa.Column("cancelled_at", sa.DateTime, nullable=True))
        b.add_column(sa.Column("cancel_reason", sa.String(500), nullable=True))
    with op.batch_alter_table("observation") as b:
        b.add_column(sa.Column("monitor_reviewed_by", sa.String(100), nullable=True))
        b.add_column(sa.Column("monitor_reviewed_at", sa.DateTime, nullable=True))
    with op.batch_alter_table("protocol") as b:
        b.add_column(sa.Column("study_locked_at", sa.DateTime, nullable=True))
        b.add_column(sa.Column("study_locked_by", sa.String(100), nullable=True))
    op.create_table(
        "signoff",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
        sa.Column("subject_ref", sa.Integer, sa.ForeignKey("subject.id"), nullable=False),
        sa.Column("visit", sa.String(200), nullable=False),
        sa.Column("signed_by", sa.String(100), nullable=False),
        sa.Column("signed_at", sa.DateTime, nullable=False),
        sa.Column("meaning", sa.String(500), nullable=False),
        sa.Column("invalidated_at", sa.DateTime, nullable=True),
        sa.Column("invalidated_by_history_id", sa.Integer, sa.ForeignKey("observation_history.id"), nullable=True),
    )
    op.create_table(
        "notification",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), nullable=False),
        sa.Column("subject", sa.String(50), nullable=True),
        sa.Column("visit", sa.String(200), nullable=True),
        sa.Column("query_id", sa.Integer, sa.ForeignKey("query.id"), nullable=True),
        sa.Column("body", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("read_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("notification")
    op.drop_table("signoff")
    with op.batch_alter_table("protocol") as b:
        b.drop_column("study_locked_by")
        b.drop_column("study_locked_at")
    with op.batch_alter_table("observation") as b:
        b.drop_column("monitor_reviewed_at")
        b.drop_column("monitor_reviewed_by")
    with op.batch_alter_table("query") as b:
        b.drop_column("cancel_reason")
        b.drop_column("cancelled_at")
        b.drop_column("close_reason")
        b.drop_column("raised_by_role")
