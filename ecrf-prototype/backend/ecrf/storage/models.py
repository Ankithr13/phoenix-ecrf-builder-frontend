from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC. SQLite drops the timezone on the way in, so comparing a
    stored value against an aware datetime raises; everything is naive UTC
    on both sides instead."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


# ------------------------------------------------------------ identity

class Organisation(Base):
    """A sponsor builds and approves forms; a site enters data for its own
    patients. The type decides which roles its users may hold and which
    portal they land in."""

    __tablename__ = "organisation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20))            # sponsor | site
    code: Mapped[str] = mapped_column(String(10), unique=True)  # BGH, used in subject codes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)   # stored lowercased
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    org_id: Mapped[int] = mapped_column(ForeignKey("organisation.id"))
    role: Mapped[str] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserSession(Base):
    """Server-side session. Only the sha256 of the cookie token is stored,
    so a copy of the database cannot be replayed as a login."""

    __tablename__ = "session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ------------------------------------------------------------ protocols

class Protocol(Base):
    """A protocol document, with the normalised text we extract from."""

    __tablename__ = "protocol"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organisation.id"))
    name: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(300))
    text_hash: Mapped[str] = mapped_column(String(64))
    normalised: Mapped[str] = mapped_column(Text)
    sections: Mapped[list] = mapped_column(JSON)       # [{number,title,start,end,page}]
    pages: Mapped[int] = mapped_column(Integer)
    tokens_estimate: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[str] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ECRFVersion(Base):
    """Draft and approved eCRFs. APPEND ONLY.

    An approval inserts a new row with version + 1 and never updates in
    place, so this table IS the version history and the audit trail.
    protocol_hash pins each version to the exact document text it came
    from, which is what makes the traceability claim hold after an
    amendment.
    """

    __tablename__ = "ecrf_version"
    __table_args__ = (UniqueConstraint("protocol_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    protocol_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)         # DraftECRF as dict
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # "draft" until an approver locks it. Content never changes after that;
    # review and extraction both refuse, so the locked row stays the latest.
    state: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProtocolSite(Base):
    """A site organisation assigned to a (locked) protocol."""

    __tablename__ = "protocol_site"
    __table_args__ = (UniqueConstraint("protocol_id", "site_org_id", name="uq_protocol_site"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    site_org_id: Mapped[int] = mapped_column(ForeignKey("organisation.id"))
    assigned_by: Mapped[str] = mapped_column(String(100))
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Subject(Base):
    """A patient at one site on one protocol. The code is made by the
    server (BGH-001), never typed, so a site cannot address a patient it
    does not own."""

    __tablename__ = "subject"
    __table_args__ = (UniqueConstraint("protocol_id", "code", name="uq_subject_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    site_org_id: Mapped[int] = mapped_column(ForeignKey("organisation.id"))
    code: Mapped[str] = mapped_column(String(50))
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Observation(Base):
    """Collected readings. Synthetic or approved de-identified data ONLY.

    repeat_num is what makes triplicate measurements storable without
    three near-identical columns, and what the statistics average over.
    """

    __tablename__ = "observation"
    __table_args__ = (UniqueConstraint("protocol_id", "subject_id", "visit",
                                       "field_name", "repeat_num"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    subject_id: Mapped[str] = mapped_column(String(50))
    visit: Mapped[str] = mapped_column(String(100))
    field_name: Mapped[str] = mapped_column(String(200))
    repeat_num: Mapped[int] = mapped_column(Integer, default=1)
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    entered_by: Mapped[str] = mapped_column(String(100))
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # subject_id stays as text so the statistics and the independent script
    # keep working; subject_ref is the row it came from.
    subject_ref: Mapped[int | None] = mapped_column(ForeignKey("subject.id"), nullable=True)
    ecrf_version_id: Mapped[int | None] = mapped_column(ForeignKey("ecrf_version.id"), nullable=True)
    # entered -> approved by the sponsor; queried while a query is open.
    status: Mapped[str] = mapped_column(String(20), default="entered", server_default="entered")
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ObservationHistory(Base):
    """One row per change to a value, written before the value changes."""

    __tablename__ = "observation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observation.id"))
    old_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_by: Mapped[str] = mapped_column(String(100))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
