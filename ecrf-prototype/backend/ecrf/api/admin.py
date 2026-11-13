"""The admin panel: people, their roles and sites, the access record, and the
two switches on each protocol's approval chain.

An admin manages the accounts of their own organisation and of every site, and
touches no clinical data. Every change writes a user_access_event row, which is
the documented record of who was granted what."""

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ecrf.auth import passwords, scope
from ecrf.auth.permissions import ROLES_FOR_ORG_TYPE, CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import (
    MonitorSite,
    Organisation,
    Protocol,
    User,
    UserAccessEvent,
    UserSession,
    utcnow,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _orgs(s: Session, cu: CurrentUser):
    return select(Organisation).where(or_(Organisation.id == cu.org.id, Organisation.type == "site"))


def _user_or_404(s: Session, cu: CurrentUser, user_id: int) -> User:
    org_ids = {o.id for o in s.scalars(_orgs(s, cu))}
    u = s.get(User, user_id)
    if u is None or u.org_id not in org_ids:
        raise HTTPException(404, "user not found")
    return u


def _event(s: Session, cu: CurrentUser, user: User, action: str, detail: str | None = None) -> None:
    s.add(UserAccessEvent(user_id=user.id, action=action, by=cu.user.email, detail=detail))


def _monitor_sites(s: Session, user_id: int) -> list[int]:
    return list(s.scalars(select(MonitorSite.site_org_id).where(MonitorSite.user_id == user_id)))


def _row(s: Session, u: User) -> dict:
    org = s.get(Organisation, u.org_id)
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "is_active": u.is_active,
            "must_change_password": u.must_change_password, "created_by": u.created_by,
            "created_at": u.created_at.isoformat(),
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "org": {"id": org.id, "name": org.name, "code": org.code, "type": org.type},
            "monitor_site_ids": _monitor_sites(s, u.id)}


def _check_role(org: Organisation, role: str) -> None:
    if role not in ROLES_FOR_ORG_TYPE[org.type]:
        raise HTTPException(422, f"{role} is not a role for a {org.type} organisation")


def _set_monitor_sites(s: Session, cu: CurrentUser, user: User, site_ids: list[int]) -> None:
    """Replace the monitor's sites, recording what changed."""
    valid = {o.id: o.code for o in s.scalars(_orgs(s, cu)) if o.type == "site"}
    unknown = [i for i in site_ids if i not in valid]
    if unknown:
        raise HTTPException(422, f"not a site: {unknown}")
    now = set(_monitor_sites(s, user.id))
    want = set(site_ids) if user.role == "monitor" else set()
    for row in s.scalars(select(MonitorSite).where(MonitorSite.user_id == user.id,
                                                    MonitorSite.site_org_id.in_(now - want))):
        s.delete(row)
    for site_id in want - now:
        s.add(MonitorSite(user_id=user.id, site_org_id=site_id, assigned_by=cu.user.email))
    if now != want:
        _event(s, cu, user, "site_assigned", "monitor sites: " + (", ".join(sorted(valid[i] for i in want)) or "none"))


# ---------------------------------------------------------------- people

@router.get("/orgs")
def orgs(cu: CurrentUser = Depends(require("users.manage")), s: Session = Depends(db.get_session)):
    return [{"id": o.id, "name": o.name, "code": o.code, "type": o.type,
             "roles": list(ROLES_FOR_ORG_TYPE[o.type])} for o in s.scalars(_orgs(s, cu).order_by(Organisation.code))]


@router.get("/users")
def list_users(org_id: int | None = None, role: str | None = None, active: bool | None = None,
               cu: CurrentUser = Depends(require("users.manage")), s: Session = Depends(db.get_session)):
    org_ids = [o.id for o in s.scalars(_orgs(s, cu))]
    q = select(User).where(User.org_id.in_(org_ids)).order_by(User.email)
    if org_id is not None:
        q = q.where(User.org_id == org_id)
    if role:
        q = q.where(User.role == role)
    if active is not None:
        q = q.where(User.is_active == active)
    return [_row(s, u) for u in s.scalars(q)]


class UserCreate(BaseModel):
    email: str
    name: str
    org_id: int
    role: str
    monitor_site_ids: list[int] = []


def _temporary_password() -> str:
    return secrets.token_urlsafe(9)


@router.post("/users")
def create_user(body: UserCreate, cu: CurrentUser = Depends(require("users.manage")),
                s: Session = Depends(db.get_session)):
    """The temporary password is in this response and nowhere else, and it
    must be changed at first login."""
    email = body.email.strip().lower()
    if "@" not in email or not body.name.strip():
        raise HTTPException(422, "A user needs a name and an email address")
    org = next((o for o in s.scalars(_orgs(s, cu)) if o.id == body.org_id), None)
    if org is None:
        raise HTTPException(404, "organisation not found")
    _check_role(org, body.role)
    if s.scalars(select(User).where(User.email == email)).first():
        raise HTTPException(409, f"{email} already has an account")
    temporary = _temporary_password()
    u = User(email=email, name=body.name.strip(), org_id=org.id, role=body.role, is_active=True,
             password_hash=passwords.hash_password(temporary), must_change_password=True,
             created_by=cu.user.email)
    s.add(u)
    s.flush()
    _event(s, cu, u, "created", f"{body.role} at {org.code}")
    _set_monitor_sites(s, cu, u, body.monitor_site_ids)
    s.commit()
    return {"user": _row(s, u), "temporary_password": temporary}


class UserEdit(BaseModel):
    role: str | None = None
    org_id: int | None = None
    monitor_site_ids: list[int] | None = None


@router.patch("/users/{user_id}")
def edit_user(user_id: int, body: UserEdit, cu: CurrentUser = Depends(require("roles.assign")),
              s: Session = Depends(db.get_session)):
    u = _user_or_404(s, cu, user_id)
    org = next((o for o in s.scalars(_orgs(s, cu)) if o.id == (body.org_id or u.org_id)), None)
    if org is None:
        raise HTTPException(404, "organisation not found")
    role = body.role or u.role
    _check_role(org, role)
    if u.id == cu.user.id and role != u.role:
        raise HTTPException(409, "You cannot change your own role")
    if role != u.role or org.id != u.org_id:
        before = f"{u.role} at {s.get(Organisation, u.org_id).code}"
        u.role, u.org_id = role, org.id
        _event(s, cu, u, "role_changed", f"{before} to {role} at {org.code}")
    if body.monitor_site_ids is not None or role != "monitor":
        _set_monitor_sites(s, cu, u, body.monitor_site_ids or [])
    s.commit()
    return _row(s, u)


def _revoke_sessions(s: Session, user_id: int) -> None:
    for row in s.scalars(select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))):
        row.revoked_at = utcnow()


@router.post("/users/{user_id}/deactivate")
def deactivate(user_id: int, cu: CurrentUser = Depends(require("users.manage")),
               s: Session = Depends(db.get_session)):
    u = _user_or_404(s, cu, user_id)
    if u.id == cu.user.id:
        raise HTTPException(409, "You cannot deactivate your own account")
    if u.is_active:
        u.is_active = False
        _revoke_sessions(s, u.id)
        _event(s, cu, u, "deactivated")
        s.commit()
    return _row(s, u)


@router.post("/users/{user_id}/reactivate")
def reactivate(user_id: int, cu: CurrentUser = Depends(require("users.manage")),
               s: Session = Depends(db.get_session)):
    u = _user_or_404(s, cu, user_id)
    if not u.is_active:
        u.is_active = True
        _event(s, cu, u, "reactivated")
        s.commit()
    return _row(s, u)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, cu: CurrentUser = Depends(require("users.manage")),
                   s: Session = Depends(db.get_session)):
    u = _user_or_404(s, cu, user_id)
    # A reset signs the person out at once, so on your own account it locks
    # you out before you can copy the temporary password.
    if u.id == cu.user.id:
        raise HTTPException(409, "Use Change password for your own account")
    temporary = _temporary_password()
    u.password_hash = passwords.hash_password(temporary)
    u.must_change_password = True
    _revoke_sessions(s, u.id)
    _event(s, cu, u, "password_reset")
    s.commit()
    return {"user": _row(s, u), "temporary_password": temporary}


@router.get("/access-log")
def access_log(user_id: int | None = None, cu: CurrentUser = Depends(require("users.manage")),
               s: Session = Depends(db.get_session)):
    org_ids = [o.id for o in s.scalars(_orgs(s, cu))]
    q = (select(UserAccessEvent, User).join(User, User.id == UserAccessEvent.user_id)
         .where(User.org_id.in_(org_ids)).order_by(UserAccessEvent.at.desc(), UserAccessEvent.id.desc()))
    if user_id is not None:
        q = q.where(UserAccessEvent.user_id == user_id)
    return [{"id": e.id, "user": u.email, "action": e.action, "by": e.by, "at": e.at.isoformat(), "detail": e.detail}
            for e, u in s.execute(q)]


# ------------------------------------------------------------------ chain

@router.get("/chain")
def chain(cu: CurrentUser = Depends(require("chain.configure")), s: Session = Depends(db.get_session)):
    return [{"id": p.id, "name": p.name, "monitor_review_required": p.monitor_review_required,
             "investigator_signature_required": p.investigator_signature_required}
            for p in s.scalars(scope.visible_protocols(cu).order_by(Protocol.uploaded_at.desc()))]


class ChainEdit(BaseModel):
    monitor_review_required: bool | None = None
    investigator_signature_required: bool | None = None


@router.put("/chain/{protocol_id}")
def set_chain(protocol_id: int, body: ChainEdit, cu: CurrentUser = Depends(require("chain.configure")),
              s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    changes = []
    for attr in ("monitor_review_required", "investigator_signature_required"):
        value = getattr(body, attr)
        if value is not None and value != getattr(p, attr):
            setattr(p, attr, value)
            changes.append(f"{attr}={value}")
    if changes:
        _event(s, cu, cu.user, "chain_configured", f"{p.name}: " + ", ".join(changes))
    s.commit()
    return {"id": p.id, "name": p.name, "monitor_review_required": p.monitor_review_required,
            "investigator_signature_required": p.investigator_signature_required}
