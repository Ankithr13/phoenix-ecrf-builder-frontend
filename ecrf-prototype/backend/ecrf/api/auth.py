"""Login, logout, and who-am-I."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth import passwords, sessions
from ecrf.auth.permissions import PERMISSIONS, CurrentUser, current_user
from ecrf.storage import db
from ecrf.storage.models import Organisation, User

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
    cu = CurrentUser(user=user, org=s.get(Organisation, user.org_id), role=user.role,
                     permissions=PERMISSIONS.get(user.role, frozenset()))
    return _me(cu)


@router.post("/logout")
def logout(request: Request, response: Response, s: Session = Depends(db.get_session)):
    sessions.end(s, request, response)
    s.commit()
    return {"ok": True}


@router.get("/me")
def me(cu: CurrentUser = Depends(current_user)):
    return _me(cu)
