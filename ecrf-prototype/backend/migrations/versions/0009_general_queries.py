"""Queries about a study, a patient or a visit, not only about one value.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-29

Adds the protocol, the site and the optional patient and visit a query is
about; the observation becomes optional. Existing queries are backfilled
from their observation.
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("query") as b:
        b.add_column(sa.Column("protocol_id", sa.Integer, nullable=True))
        b.add_column(sa.Column("site_org_id", sa.Integer, nullable=True))
        b.add_column(sa.Column("subject_ref", sa.Integer, nullable=True))
        b.add_column(sa.Column("visit", sa.String(200), nullable=True))
        b.alter_column("observation_id", existing_type=sa.Integer, nullable=True)
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE "query" SET
            protocol_id = (SELECT protocol_id FROM observation WHERE observation.id = "query".observation_id),
            subject_ref = (SELECT subject_ref FROM observation WHERE observation.id = "query".observation_id)
        WHERE observation_id IS NOT NULL"""))
    conn.execute(sa.text("""
        UPDATE "query" SET
            site_org_id = (SELECT site_org_id FROM subject WHERE subject.id = "query".subject_ref)
        WHERE subject_ref IS NOT NULL"""))
    with op.batch_alter_table("query") as b:
        b.alter_column("protocol_id", existing_type=sa.Integer, nullable=False)
        b.alter_column("site_org_id", existing_type=sa.Integer, nullable=False)
        b.create_foreign_key("fk_query_protocol_id_protocol", "protocol", ["protocol_id"], ["id"])
        b.create_foreign_key("fk_query_site_org_id_organisation", "organisation", ["site_org_id"], ["id"])
        b.create_foreign_key("fk_query_subject_ref_subject", "subject", ["subject_ref"], ["id"])


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text('DELETE FROM "query" WHERE observation_id IS NULL'))
    with op.batch_alter_table("query") as b:
        b.drop_constraint("fk_query_subject_ref_subject", type_="foreignkey")
        b.drop_constraint("fk_query_site_org_id_organisation", type_="foreignkey")
        b.drop_constraint("fk_query_protocol_id_protocol", type_="foreignkey")
        b.alter_column("observation_id", existing_type=sa.Integer, nullable=False)
        for col in ("visit", "subject_ref", "site_org_id", "protocol_id"):
            b.drop_column(col)
