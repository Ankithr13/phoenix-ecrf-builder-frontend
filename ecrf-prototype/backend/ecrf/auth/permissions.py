"""The permission table and the one dependency that enforces it.

This file is the only place a role is ever compared to anything. An
endpoint declares what it needs with require("perm") and gets the signed-in
user back; whether that user may see a particular row is the scope
helpers' job, and a row outside their scope is a 404, never a 403, so
nobody can learn that it exists."""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ecrf.auth import sessions
from ecrf.storage import db
from ecrf.storage.models import Organisation, User

PERMISSIONS: dict[str, frozenset[str]] = {
    "builder": frozenset({
        "protocol.view", "protocol.upload", "protocol.extract", "form.edit",
        "data.view", "query.raise", "query.close", "stats.view", "data.seed",
    }),
    "approver": frozenset({
        "protocol.view", "protocol.upload", "protocol.extract", "form.edit",
        "form.lock", "site.assign", "data.view", "data.approve",
        "query.raise", "query.close", "stats.view", "data.seed",
    }),
    "site_staff": frozenset({
        "study.view", "subject.create", "data.enter", "data.view", "query.answer",
    }),
}

ROLES_FOR_ORG_TYPE: dict[str, tuple[str, ...]] = {
    "sponsor": ("builder", "approver"),
    "site": ("site_staff",),
}


@dataclass(frozen=True)
class CurrentUser:
    user: User
    org: Organisation
    role: str
    permissions: frozenset[str]

    def can(self, perm: str) -> bool:
        return perm in self.permissions


def _load(request: Request, s: Session) -> CurrentUser:
    user = sessions.user_for_request(s, request)
    if user is None:
        raise HTTPException(401, "Sign in to continue")
    org = s.get(Organisation, user.org_id)
    return CurrentUser(user=user, org=org, role=user.role,
                       permissions=PERMISSIONS.get(user.role, frozenset()))


def current_user(request: Request, s: Session = Depends(db.get_session)) -> CurrentUser:
    """A signed-in user with no permission requirement. Used by /me."""
    return _load(request, s)


def require(*perms: str):
    """Dependency: the caller must hold at least one of the named
    permissions. Most endpoints name exactly one; the few shared between
    portals name one per side."""
    def dep(request: Request, s: Session = Depends(db.get_session)) -> CurrentUser:
        cu = _load(request, s)
        if not any(cu.can(p) for p in perms):
            raise HTTPException(403, f"Your role ({cu.role}) cannot do this")
        return cu
    return dep
