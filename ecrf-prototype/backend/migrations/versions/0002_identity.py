"""Organisations, users, sessions; protocols belong to an organisation.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22

Existing protocols are handed to the demo sponsor organisation, which this
migration creates if it is not there, so the column can be NOT NULL.
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organisation",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("code", sa.String(10), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "user",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(200), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(300), nullable=False),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organisation.id"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_login_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "session",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
    )

    bind = op.get_bind()
    org_id = bind.execute(sa.text("SELECT id FROM organisation WHERE code = 'PHX'")).scalar()
    if org_id is None:
        bind.execute(sa.text(
            "INSERT INTO organisation (name, type, code, created_at) "
            "VALUES ('Phoenix Clinical Demo', 'sponsor', 'PHX', CURRENT_TIMESTAMP)"))
        org_id = bind.execute(sa.text("SELECT id FROM organisation WHERE code = 'PHX'")).scalar()

    # Batch mode rebuilds the table on SQLite, and every constraint it
    # carries over must have a name, so the FK is created explicitly.
    with op.batch_alter_table("protocol") as b:
        b.add_column(sa.Column("org_id", sa.Integer, nullable=True))
    bind.execute(sa.text("UPDATE protocol SET org_id = :o WHERE org_id IS NULL"), {"o": org_id})
    with op.batch_alter_table("protocol") as b:
        b.alter_column("org_id", existing_type=sa.Integer, nullable=False)
        b.create_foreign_key("fk_protocol_org_id_organisation", "organisation", ["org_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("protocol") as b:
        b.drop_constraint("fk_protocol_org_id_organisation", type_="foreignkey")
        b.drop_column("org_id")
    op.drop_table("session")
    op.drop_table("user")
    op.drop_table("organisation")
