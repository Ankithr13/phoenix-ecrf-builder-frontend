"""The permission table and the one dependency that enforces it.

This file is the only place a role is ever compared to anything. An
endpoint declares what it needs with require("perm") and gets the signed-in
user back; whether that user may see a particular row is the scope
helpers' job, and a row outside their scope is a 404, never a 403, so
nobody can learn that it exists."""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth import sessions
from ecrf.storage import db
from ecrf.storage.models import MonitorSite, Organisation, User

# The matrix agreed for Sprint 3, from the client's EDC roles document. It
# asks for least privilege, admin kept apart from clinical data, and signature
# authority limited to investigators. tests/test_permissions.py asserts it cell
# by cell, so a change here has to be a change there too.
SPONSOR_ROLES = ("admin", "builder", "data_manager", "monitor", "read_only")
SITE_ROLES = ("investigator", "site_coordinator", "site_data_entry")

_EVERYONE = (*SPONSOR_ROLES, *SITE_ROLES)
_MATRIX: dict[str, tuple[str, ...]] = {
    "protocol.upload": ("builder",),
    "protocol.extract": ("builder",),
    "form.edit": ("builder",),
    "protocol.lock": ("data_manager",),
    "protocol.view": _EVERYONE,
    "sites.assign": ("admin", "data_manager"),
    "subject.create": ("site_coordinator",),
    "data.enter": SITE_ROLES,
    "data.submit": SITE_ROLES,
    "data.approve": ("data_manager",),
    "data.monitor_review": ("monitor",),
    "query.raise": ("data_manager", "monitor", "investigator", "site_coordinator"),
    "query.answer": SITE_ROLES,
    "query.close": ("data_manager", "monitor"),
    "signoff.sign": ("investigator",),
    "dashboard.view": ("admin", "builder", "data_manager", "monitor", "investigator", "site_coordinator", "read_only"),
    "listing.view": ("data_manager", "monitor", "investigator", "site_coordinator"),
    "listing.export": ("data_manager", "monitor", "investigator", "site_coordinator"),
    "report.pdf": ("builder", "data_manager", "monitor", "investigator", "site_coordinator", "read_only"),
    "sap.edit": ("data_manager",),
    "users.manage": ("admin",),
    "roles.assign": ("admin",),
    "chain.configure": ("admin",),
    "study.lock": ("admin", "data_manager"),
}

PERMISSIONS: dict[str, frozenset[str]] = {
    role: frozenset(perm for perm, roles in _MATRIX.items() if role in roles) for role in _EVERYONE
}

ROLES_FOR_ORG_TYPE: dict[str, tuple[str, ...]] = {"sponsor": SPONSOR_ROLES, "site": SITE_ROLES}

# Who may read entered values row by row. Everyone who works with them; not
# the admin, the builder or the read-only role, who see totals on the dashboard.
DATA_READERS = ("listing.view", "data.enter", "data.approve")


@dataclass(frozen=True)
class CurrentUser:
    user: User
    org: Organisation
    role: str
    permissions: frozenset[str]
    # The sites whose data this person may see. None means every site on the
    # sponsor's studies. A site role has its own organisation; a monitor has
    # the sites assigned in monitor_site.
    site_ids: frozenset[int] | None = None

    def can(self, perm: str) -> bool:
        return perm in self.permissions


def site_scope(s: Session, user: User, org: Organisation) -> frozenset[int] | None:
    if org.type == "site":
        return frozenset({org.id})
    if user.role == "monitor":
        return frozenset(s.scalars(select(MonitorSite.site_org_id).where(MonitorSite.user_id == user.id)))
    return None


def build(s: Session, user: User) -> CurrentUser:
    org = s.get(Organisation, user.org_id)
    return CurrentUser(user=user, org=org, role=user.role,
                       permissions=PERMISSIONS.get(user.role, frozenset()),
                       site_ids=site_scope(s, user, org))


def _load(request: Request, s: Session) -> CurrentUser:
    user = sessions.user_for_request(s, request)
    if user is None:
        raise HTTPException(401, "Sign in to continue")
    return build(s, user)


def current_user(request: Request, s: Session = Depends(db.get_session)) -> CurrentUser:
    """A signed-in user with no permission requirement. Used only by /me and
    the change-password route, the two a temporary password may reach."""
    return _load(request, s)


def require(*perms: str):
    """Dependency: the caller must hold at least one of the named
    permissions. Most endpoints name exactly one; the few shared between
    portals name one per side."""
    def dep(request: Request, s: Session = Depends(db.get_session)) -> CurrentUser:
        cu = _load(request, s)
        # A temporary password opens only the change-password screen.
        if cu.user.must_change_password:
            raise HTTPException(403, {"code": "must_change_password",
                                      "message": "Choose a new password to continue"})
        if not any(cu.can(p) for p in perms):
            raise HTTPException(403, f"Your role ({cu.role}) cannot do this")
        return cu
    return dep
