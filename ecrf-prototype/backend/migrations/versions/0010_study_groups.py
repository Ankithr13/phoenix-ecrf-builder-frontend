import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organisation.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("org_id", "code", name="uq_study_org_code"),
    )
    op.create_table(
        "study_protocol",
        sa.Column("protocol_id", sa.Integer, sa.ForeignKey("protocol.id"), primary_key=True),
        sa.Column("study_id", sa.Integer, sa.ForeignKey("study.id"), nullable=False),
        sa.Column("assigned_by", sa.String(200), nullable=False),
        sa.Column("assigned_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_study_protocol_study_id", "study_protocol", ["study_id"])


def downgrade() -> None:
    op.drop_index("ix_study_protocol_study_id", table_name="study_protocol")
    op.drop_table("study_protocol")
    op.drop_table("study")
