"""Registration details on a subject.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-29

Initials, year of birth, sex, enrolment date and a note. Deliberately not a
name or a full date of birth: a case report form is pseudonymous and the
code-to-person link belongs in the site's own enrolment log.
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subject") as b:
        b.add_column(sa.Column("initials", sa.String(5), nullable=True))
        b.add_column(sa.Column("birth_year", sa.Integer, nullable=True))
        b.add_column(sa.Column("sex", sa.String(20), nullable=True))
        b.add_column(sa.Column("enrolled_on", sa.String(10), nullable=True))
        b.add_column(sa.Column("note", sa.String(500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("subject") as b:
        for col in ("note", "enrolled_on", "sex", "birth_year", "initials"):
            b.drop_column(col)
