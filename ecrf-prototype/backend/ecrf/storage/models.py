from datetime import datetime

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
    false,
    true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ecrf import clock


def utcnow() -> datetime:
    """Naive UTC, from the app's one clock (see ecrf/clock.py)."""
    return clock.now()


# The query statuses that are still waiting on someone. Closed and cancelled are not.
LIVE_QUERY = ("open", "answered")


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
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MonitorSite(Base):
    """A site a monitor may see. A monitor with no rows here sees no site data."""

    __tablename__ = "monitor_site"
    __table_args__ = (UniqueConstraint("user_id", "site_org_id", name="uq_monitor_site"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    site_org_id: Mapped[int] = mapped_column(ForeignKey("organisation.id"))
    assigned_by: Mapped[str] = mapped_column(String(100))
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserAccessEvent(Base):
    """The record of who was granted what, which the client's roles document
    asks for: created, role_changed, deactivated, reactivated, password_reset,
    password_changed, site_assigned, chain_configured. Append only."""

    __tablename__ = "user_access_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    action: Mapped[str] = mapped_column(String(40))
    by: Mapped[str] = mapped_column(String(100))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)


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
    filename: Mapped[str] = mapped_column(String(300))        # as uploaded, never used as a path
    stored_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)  # <uuid>.pdf
    text_hash: Mapped[str] = mapped_column(String(64))
    normalised: Mapped[str] = mapped_column(Text)
    sections: Mapped[list] = mapped_column(JSON)       # [{number,title,start,end,page}]
    pages: Mapped[int] = mapped_column(Integer)
    tokens_estimate: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[str] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Pass one's answer, {visits, forms, usage}, kept so a person can
    # correct the visit list before the per-visit calls are paid for.
    extraction_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # The two switches on the approval chain. The order itself is fixed:
    # enter, submit, monitor review if required, data manager approval,
    # investigator sign-off if required, study lock.
    monitor_review_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    investigator_signature_required: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    study_locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    study_locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class LLMCall(Base):
    """One row per distinct request ever sent to a model. The key is the
    sha256 of everything that could change the answer, so an identical
    request is answered from here and costs nothing."""

    __tablename__ = "llm_call"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    model: Mapped[str] = mapped_column(String(200))
    request_json: Mapped[dict] = mapped_column(JSON)
    response_text: Mapped[str] = mapped_column(Text)
    usage_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    hits: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


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


class FieldComment(Base):
    """A reviewer's note on one field. Keyed by the stable field_id, so a
    comment survives new versions and a rename."""

    __tablename__ = "field_comment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    version: Mapped[int] = mapped_column(Integer)
    field_id: Mapped[str] = mapped_column(String(32))
    author: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class FormFieldHistory(Base):
    """One row per change to one attribute of one field: the old value, the new
    one, who, when and why. Versions hold whole snapshots; this says what moved
    between them. field_id is empty for a change to the form itself, such as
    the lock."""

    __tablename__ = "form_field_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    version: Mapped[int] = mapped_column(Integer)
    field_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attribute: Mapped[str] = mapped_column(String(40))
    old_value: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    by: Mapped[str] = mapped_column(String(100))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class EditCheck(Base):
    """One edit check on one protocol, as data. Built-in ones are generated at
    lock; a builder can add more of the same types. Soft checks raise a query,
    hard checks block the save, and only format checks are hard."""

    __tablename__ = "edit_check"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    code: Mapped[str] = mapped_column(String(20))            # EC-006, FMT, REQ, CUSTOM-1
    form: Mapped[str | None] = mapped_column(String(200), nullable=True)  # visit; None spans visits
    field_ids: Mapped[list] = mapped_column(JSON)
    type: Mapped[str] = mapped_column(String(20))
    logic: Mapped[dict] = mapped_column(JSON)
    message: Mapped[str] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(10))        # soft | hard
    owner: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    origin: Mapped[str] = mapped_column(String(10))          # builtin | custom
    form_version: Mapped[int] = mapped_column(Integer)


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
    """A patient at one site on one protocol. The code is namespaced by the
    site (BGH-001): the server makes it unless the site supplies one with
    its own prefix, so a site can never address another site's patient.

    What is stored at registration is what a case report form may hold:
    the study code, year of birth, sex and the enrolment date.
    Never a name, full date of birth or any contact detail; the link from
    code to person lives in the site's own enrolment log, not here."""

    __tablename__ = "subject"
    __table_args__ = (UniqueConstraint("protocol_id", "code", name="uq_subject_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    site_org_id: Mapped[int] = mapped_column(ForeignKey("organisation.id"))
    code: Mapped[str] = mapped_column(String(50))
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    enrolled_on: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO date
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
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
    # draft -> submitted -> monitor_reviewed if required -> approved. An open
    # query does not change this; it is counted alongside and blocks approval.
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    # value, not_done, not_applicable or unknown. Anything but value has a reason.
    completion_status: Mapped[str] = mapped_column(String(20), default="value", server_default="value")
    completion_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    monitor_reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    monitor_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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


class Query(Base):
    """A question raised by either side about a study, a patient, a visit
    or one entered value. It always belongs to one protocol and one site
    (the site that asked, the patient's site, or the site a sponsor chose
    to ask), which is what keeps a site's traffic its own. The other side
    answers (a site may attach a corrected value when the query is about
    one value; a sponsor cannot, data entry is the site's job) and the side
    that raised it closes it, which sends a queried value back to 'entered'
    so it is approved again on purpose. `raised_by_org` is the
    organisation type that asked, which decides who answers and who closes."""

    __tablename__ = "query"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    site_org_id: Mapped[int] = mapped_column(ForeignKey("organisation.id"))
    subject_ref: Mapped[int | None] = mapped_column(ForeignKey("subject.id"), nullable=True)
    visit: Mapped[str | None] = mapped_column(String(200), nullable=True)
    observation_id: Mapped[int | None] = mapped_column(ForeignKey("observation.id"), nullable=True)
    raised_by: Mapped[str] = mapped_column(String(100))
    raised_by_org: Mapped[str] = mapped_column(String(20), default="sponsor", server_default="sponsor")  # sponsor | site
    raised_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    text: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")  # open | answered | closed | cancelled
    answer_text: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    answered_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Set on a query raised by an edit check. check_key names the check row, and
    # is what stops the same failure raising a second query.
    check_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    check_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    raised_by_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Signoff(Base):
    """An investigator's sign-off on one patient's visit: a recorded action with
    who, when and the meaning statement. Any later change to a signed value sets
    invalidated_at, and the visit needs signing again. The row stays."""

    __tablename__ = "signoff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    subject_ref: Mapped[int] = mapped_column(ForeignKey("subject.id"))
    visit: Mapped[str] = mapped_column(String(200))
    signed_by: Mapped[str] = mapped_column(String(100))
    signed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    meaning: Mapped[str] = mapped_column(String(500))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    invalidated_by_history_id: Mapped[int | None] = mapped_column(ForeignKey("observation_history.id"), nullable=True)


class Notification(Base):
    """One in-app message for one person. No email, no SMS."""

    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    kind: Mapped[str] = mapped_column(String(30))
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    subject: Mapped[str | None] = mapped_column(String(50), nullable=True)
    visit: Mapped[str | None] = mapped_column(String(200), nullable=True)
    query_id: Mapped[int | None] = mapped_column(ForeignKey("query.id"), nullable=True)
    body: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SapItem(Base):
    """One row of the statistical analysis plan: which field and which visits a
    fixed calculation works on. It mirrors the client's traceability matrix.
    Visits have no table of their own, so the two visit columns hold the visit's
    name, as observation.visit does."""

    __tablename__ = "sap_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocol.id"))
    label: Mapped[str] = mapped_column(String(200))  # the matrix's "SAP Item"
    endpoint_concept: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))  # endpoint, safety, disposition or baseline
    field_id: Mapped[str] = mapped_column(String(32))
    baseline_visit_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    analysis_visit_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # {"on": "change" or "analysis", "op": "<=", "value": -10}
    responder_rule: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    method: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Filled from the chosen field and calculation; null on rows made before that.
    form: Mapped[str | None] = mapped_column(String(200), nullable=True)
    derivation: Mapped[str | None] = mapped_column(Text, nullable=True)

