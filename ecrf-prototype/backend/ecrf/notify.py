"""In-app notifications. No email and no SMS, on purpose.

Each function here is one event, and decides who hears about it. A row is written
for each person, in the same transaction as the thing that happened.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth.permissions import PERMISSIONS
from ecrf.storage.models import MonitorSite, Notification, Protocol, ProtocolSite, Query, User

KINDS = ("query_raised", "query_answered", "system_query", "visit_submitted", "visit_approved",
         "signoff_needed", "signoff_invalidated", "form_locked", "study_locked")


def _people(s: Session, org_id: int, perm: str | None = None) -> list[User]:
    users = s.scalars(select(User).where(User.org_id == org_id, User.is_active.is_(True))).all()
    return [u for u in users if perm is None or perm in PERMISSIONS.get(u.role, frozenset())]


def _monitors(s: Session, p: Protocol, site_id: int) -> list[User]:
    """Monitors on the sponsor side assigned to this site."""
    return [u for u in _people(s, p.org_id, "data.monitor_review")
            if s.scalars(select(MonitorSite.id).where(MonitorSite.user_id == u.id,
                                                       MonitorSite.site_org_id == site_id)).first()]


def _send(s: Session, users: list[User], kind: str, p: Protocol, body: str, subject: str | None = None,
          visit: str | None = None, query_id: int | None = None) -> None:
    # Only roles with an inbox hear anything. The admin has none.
    readers = {u.id for u in users if "notifications.view" in PERMISSIONS.get(u.role, frozenset())}
    for user_id in readers:
        s.add(Notification(user_id=user_id, kind=kind, protocol_id=p.id, subject=subject, visit=visit,
                           query_id=query_id, body=body))


def query_raised(s: Session, p: Protocol, q: Query, subject: str | None) -> None:
    """A person asked. The other side hears: the site's staff, or the sponsor."""
    if q.raised_by_org == "sponsor":
        users = _people(s, q.site_org_id, "query.answer")
    else:
        users = [*_people(s, p.org_id, "data.approve"), *_monitors(s, p, q.site_org_id)]
    _send(s, users, "query_raised", p, f"New query: {q.text}", subject, q.visit, q.id)


def query_answered(s: Session, p: Protocol, q: Query, subject: str | None) -> None:
    """Whoever asked hears. A system query has no person, so the data manager does."""
    users = list(s.scalars(select(User).where(User.email == q.raised_by, User.is_active.is_(True))))
    if not users:
        users = _people(s, p.org_id, "data.approve")
    _send(s, users, "query_answered", p, f"Your query was answered: {q.text}", subject, q.visit, q.id)


def system_query(s: Session, p: Protocol, q: Query, subject: str | None, visit: str) -> None:
    _send(s, _people(s, q.site_org_id, "query.answer"), "system_query", p, f"An edit check raised a query: {q.text}",
          subject, visit, q.id)


def visit_submitted(s: Session, p: Protocol, site_id: int, subject: str, visit: str) -> None:
    users = [*_people(s, p.org_id, "data.approve"), *_monitors(s, p, site_id)]
    _send(s, users, "visit_submitted", p, f"{subject} {visit} was submitted", subject, visit)


def visit_approved(s: Session, p: Protocol, site_id: int, subject: str, visit: str) -> None:
    _send(s, _people(s, site_id, "data.enter"), "visit_approved", p, f"{subject} {visit} was approved", subject, visit)


def signoff_needed(s: Session, p: Protocol, site_id: int, subject: str, visit: str) -> None:
    _send(s, _people(s, site_id, "signoff.sign"), "signoff_needed", p, f"{subject} {visit} is ready for your sign-off",
          subject, visit)


def signoff_invalidated(s: Session, p: Protocol, site_id: int, subject: str, visit: str) -> None:
    _send(s, _people(s, site_id, "signoff.sign"), "signoff_invalidated", p,
          f"A value changed after you signed {subject} {visit}. It needs signing again.", subject, visit)


def form_locked(s: Session, p: Protocol, site_ids: list[int] | None = None) -> None:
    """To the sites on the study. A site is assigned after the lock, so this
    fires at assignment as well as at the lock."""
    if site_ids is None:
        site_ids = list(s.scalars(select(ProtocolSite.site_org_id).where(ProtocolSite.protocol_id == p.id)))
    for site_id in site_ids:
        _send(s, _people(s, site_id), "form_locked", p, f"The form for {p.name} is locked and ready for data entry")


def study_locked(s: Session, p: Protocol) -> None:
    """Everyone on the study."""
    site_ids = s.scalars(select(ProtocolSite.site_org_id).where(ProtocolSite.protocol_id == p.id))
    users = _people(s, p.org_id)
    for site_id in site_ids:
        users += _people(s, site_id)
    _send(s, users, "study_locked", p, f"{p.name} is locked. No further data can be changed.")
