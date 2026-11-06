"""Login, logout, and who-am-I."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth import passwords, sessions
from ecrf.auth.permissions import CurrentUser, build, current_user
from ecrf.storage import db
from ecrf.storage.models import User, UserAccessEvent

router = APIRouter(prefix="/api/auth", tags=["auth"])

WRONG = "Email or password is incorrect"


class LoginRequest(BaseModel):
    email: str
    password: str


def _me(cu: CurrentUser) -> dict:
    return {
        "user": {"id": cu.user.id, "name": cu.user.name, "email": cu.user.email},
        "org": {"id": cu.org.id, "name": cu.org.name, "type": cu.org.type, "code": cu.org.code},
        "role": cu.role,
        "permissions": sorted(cu.permissions),
        "must_change_password": cu.user.must_change_password,
    }


@router.post("/login")
def login(body: LoginRequest, response: Response, s: Session = Depends(db.get_session)):
    email = body.email.strip().lower()
    if sessions.too_many_failures(email):
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    user = s.scalars(select(User).where(User.email == email)).first()
    # One message for every failure, so the form cannot be used to find out
    # which emails have accounts.
    if (user is None or not user.is_active
            or not passwords.verify_password(body.password, user.password_hash)):
        sessions.record_failure(email)
        raise HTTPException(401, WRONG)
    sessions.clear_failures(email)
    sessions.start(s, user, response)
    s.commit()
    return _me(build(s, user))


@router.post("/logout")
def logout(request: Request, response: Response, s: Session = Depends(db.get_session)):
    sessions.end(s, request, response)
    s.commit()
    return {"ok": True}


@router.get("/me")
def me(cu: CurrentUser = Depends(current_user)):
    return _me(cu)


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(body: ChangePassword, cu: CurrentUser = Depends(current_user),
                    s: Session = Depends(db.get_session)):
    """Open to any signed-in user, and the one thing a temporary password can do."""
    user = s.get(User, cu.user.id)
    if not passwords.verify_password(body.current_password, user.password_hash):
        raise HTTPException(403, "Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(422, "A new password needs at least 8 characters")
    if body.new_password == body.current_password:
        raise HTTPException(422, "Choose a password different from the current one")
    user.password_hash = passwords.hash_password(body.new_password)
    user.must_change_password = False
    s.add(UserAccessEvent(user_id=user.id, action="password_changed", by=user.email))
    s.commit()
    return _me(build(s, user))
