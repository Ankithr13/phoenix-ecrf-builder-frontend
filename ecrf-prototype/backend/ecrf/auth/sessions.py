"""Cookie sessions.

The browser holds a random token in an httpOnly cookie; the database holds
only its sha256. Expiry and revocation are checked on every request, and a
disabled account is refused even with a live session."""

import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.config import config
from ecrf.storage.models import User, UserSession, utcnow

COOKIE = "ecrf_session"

# Login failures per email in the last window. In memory on purpose: one
# process, one prototype. A multi-worker deployment moves this to the DB.
_WINDOW_SECONDS = 15 * 60
_MAX_FAILURES = 5
_failures: dict[str, deque] = defaultdict(deque)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def too_many_failures(email: str) -> bool:
    q = _failures[email]
    cutoff = time.monotonic() - _WINDOW_SECONDS
    while q and q[0] < cutoff:
        q.popleft()
    return len(q) >= _MAX_FAILURES


def record_failure(email: str) -> None:
    _failures[email].append(time.monotonic())


def clear_failures(email: str) -> None:
    _failures.pop(email, None)


def start(s: Session, user: User, response: Response) -> UserSession:
    token = secrets.token_urlsafe(32)
    row = UserSession(user_id=user.id, token_hash=_hash(token),
                      expires_at=utcnow() + timedelta(hours=config.session_hours))
    user.last_login_at = utcnow()
    s.add(row)
    s.flush()
    response.set_cookie(
        COOKIE, token, max_age=config.session_hours * 3600, httponly=True,
        samesite="lax", secure=config.cookie_secure, path="/",
    )
    return row


def end(s: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        row = s.scalars(select(UserSession).where(UserSession.token_hash == _hash(token))).first()
        if row and row.revoked_at is None:
            row.revoked_at = utcnow()
    response.delete_cookie(COOKIE, path="/")


def user_for_request(s: Session, request: Request) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    now = utcnow()
    row = s.scalars(select(UserSession).where(
        UserSession.token_hash == _hash(token),
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > now,
    )).first()
    if row is None:
        return None
    user = s.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    return user
