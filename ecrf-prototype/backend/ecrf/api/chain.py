"""The later links of the approval chain: monitor review, investigator sign-off,
study lock. And the in-app notifications that follow them.

Investigator sign-off is a recorded action: who, when, the meaning statement,
and a password entered again. It is not an electronic signature in any
regulatory sense, and nothing here should call it one."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf import notify
from ecrf.auth import passwords, scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import (
    LIVE_QUERY,
    FormFieldHistory,
    Notification,
    Observation,
    Protocol,
    Query,
    Signoff,
    Subject,
    utcnow,
)

router = APIRouter(tags=["approval chain"])

MEANING = "I confirm this visit's data is complete and accurate to the best of my knowledge"


# ---------------------------------------------------------- monitor review

class VisitRef(BaseModel):
    subject_id: str
    visit: str


@router.post("/api/protocols/{protocol_id}/monitor-review")
def monitor_review(protocol_id: int, body: VisitRef, cu: CurrentUser = Depends(require("data.monitor_review")),
                   s: Session = Depends(db.get_session)):
    """Mark a submitted visit reviewed, for a site assigned to this monitor."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    scope.check_study_open(p)
    subj = scope.subject_or_404(s, cu, protocol_id, body.subject_id)
    rows = list(s.scalars(select(Observation).where(Observation.protocol_id == protocol_id,
                                                    Observation.subject_ref == subj.id,
                                                    Observation.visit == body.visit,
                                                    Observation.status == "submitted")))
    if not rows:
        raise HTTPException(409, "Nothing at this visit is waiting for review")
    now = utcnow()
    for o in rows:
        o.status, o.monitor_reviewed_by, o.monitor_reviewed_at = "monitor_reviewed", cu.user.email, now
    s.commit()
    return {"reviewed": len(rows)}


# ---------------------------------------------------------------- sign-off

def _row(sg: Signoff, code: str) -> dict:
    return {"id": sg.id, "subject": code, "visit": sg.visit, "signed_by": sg.signed_by,
            "signed_at": sg.signed_at.isoformat(), "meaning": sg.meaning,
            "invalidated_at": sg.invalidated_at.isoformat() if sg.invalidated_at else None}


def valid_signoff(s: Session, subject_ref: int, visit: str) -> Signoff | None:
    return s.scalars(select(Signoff).where(Signoff.subject_ref == subject_ref, Signoff.visit == visit,
                                           Signoff.invalidated_at.is_(None))).first()


class SignRequest(VisitRef):
    password: str


@router.post("/api/protocols/{protocol_id}/signoff")
def sign(protocol_id: int, body: SignRequest, cu: CurrentUser = Depends(require("signoff.sign")),
         s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    scope.check_study_open(p)
    subj = scope.subject_or_404(s, cu, protocol_id, body.subject_id)
    if not p.investigator_signature_required:
        raise HTTPException(409, "This study does not use investigator sign-off")
    if not passwords.verify_password(body.password, cu.user.password_hash):
        raise HTTPException(403, "That password is not correct")
    rows = list(s.scalars(select(Observation).where(Observation.protocol_id == protocol_id,
                                                    Observation.subject_ref == subj.id,
                                                    Observation.visit == body.visit)))
    if not rows:
        raise HTTPException(409, "Nothing has been entered at this visit")
    waiting = [o.field_name for o in rows if o.status != "approved"]
    if waiting:
        raise HTTPException(409, {"message": "Every value must be approved before sign-off", "waiting": waiting})
    live = s.scalars(select(Query.id).where(Query.subject_ref == subj.id, Query.status.in_(LIVE_QUERY))).all()
    if live:
        raise HTTPException(409, {"message": "All queries on this patient must be closed before sign-off",
                                  "open_queries": len(live)})
    if valid_signoff(s, subj.id, body.visit):
        raise HTTPException(409, "This visit is already signed")
    sg = Signoff(protocol_id=protocol_id, subject_ref=subj.id, visit=body.visit, signed_by=cu.user.email, meaning=MEANING)
    s.add(sg)
    s.commit()
    return _row(sg, subj.code)


@router.get("/api/protocols/{protocol_id}/signoffs")
def signoffs(protocol_id: int, subject_id: str | None = None,
             cu: CurrentUser = Depends(require("listing.view", "data.enter")),
             s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    subjects = {x.id: x.code for x in s.scalars(scope.visible_subjects(cu, protocol_id))}
    rows = s.scalars(select(Signoff).where(Signoff.protocol_id == protocol_id).order_by(Signoff.signed_at.desc()))
    return {"meaning": MEANING, "rows": [
        _row(sg, subjects[sg.subject_ref]) for sg in rows
        if sg.subject_ref in subjects and (not subject_id or subjects[sg.subject_ref] == subject_id)]}


# -------------------------------------------------------------- study lock

def lock_blockers(s: Session, p: Protocol) -> list[str]:
    """Why this study cannot be locked yet. Empty means it can."""
    out = []
    if db.locked_version(s, p.id) is None:
        out.append("The form is not locked")
    live = s.scalars(select(Query.id).where(Query.protocol_id == p.id, Query.status.in_(LIVE_QUERY))).all()
    if live:
        out.append(f"{len(live)} open quer{'y' if len(live) == 1 else 'ies'}")
    rows = list(s.scalars(select(Observation).where(Observation.protocol_id == p.id)))
    waiting = [o for o in rows if o.status != "approved"]
    if waiting:
        out.append(f"{len(waiting)} value(s) not approved")
    if p.investigator_signature_required:
        codes = {x.id: x.code for x in s.scalars(select(Subject).where(Subject.protocol_id == p.id))}
        visits = {(o.subject_ref, o.visit) for o in rows if o.subject_ref}
        unsigned = sorted(f"{codes.get(ref, ref)} {visit}" for ref, visit in visits if not valid_signoff(s, ref, visit))
        if unsigned:
            out.append(f"{len(unsigned)} visit(s) not signed: {', '.join(unsigned[:5])}")
    return out


@router.get("/api/protocols/{protocol_id}/study-lock")
def study_lock_state(protocol_id: int, cu: CurrentUser = Depends(require("study.lock")),
                     s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    return {"locked": p.study_locked_at is not None, "locked_by": p.study_locked_by,
            "locked_at": p.study_locked_at.isoformat() if p.study_locked_at else None,
            "blockers": [] if p.study_locked_at else lock_blockers(s, p)}


@router.post("/api/protocols/{protocol_id}/study-lock")
def study_lock(protocol_id: int, cu: CurrentUser = Depends(require("study.lock")),
               s: Session = Depends(db.get_session)):
    """After this, every write to this study's data returns 409."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    if p.study_locked_at is not None:
        return {"locked": True, "locked_by": p.study_locked_by}
    blockers = lock_blockers(s, p)
    if blockers:
        raise HTTPException(409, {"message": "The study cannot be locked yet", "blockers": blockers})
    p.study_locked_at, p.study_locked_by = utcnow(), cu.user.email
    v = db.latest_version(s, protocol_id)
    s.add(FormFieldHistory(protocol_id=protocol_id, version=v.version, field_id=None, attribute="study_lock",
                           old_value="open", new_value="locked", by=cu.user.email))
    notify.study_locked(s, p)
    s.commit()
    return {"locked": True, "locked_by": p.study_locked_by}


# ----------------------------------------------------------- notifications

def _note(n: Notification, names: dict[int, str]) -> dict:
    return {"id": n.id, "kind": n.kind, "protocol_id": n.protocol_id, "protocol_name": names.get(n.protocol_id),
            "subject": n.subject, "visit": n.visit, "query_id": n.query_id, "body": n.body,
            "created_at": n.created_at.isoformat(), "read_at": n.read_at.isoformat() if n.read_at else None}


def _inbox(cu: CurrentUser, *columns):
    """One's own notifications. A monitor's are limited to the protocols they can
    still see, so a study they no longer cover drops out of the inbox."""
    q = select(*columns) if columns else select(Notification)
    q = q.where(Notification.user_id == cu.user.id)
    if cu.role == "monitor":
        q = q.where(Notification.protocol_id.in_(scope.visible_protocols(cu).with_only_columns(Protocol.id)))
    return q


@router.get("/api/notifications")
def notifications(protocol_id: int | None = None, kind: str | None = None,
                  cu: CurrentUser = Depends(require("notifications.view")), s: Session = Depends(db.get_session)):
    """One's own, unread first."""
    q = _inbox(cu)
    if protocol_id is not None:
        q = q.where(Notification.protocol_id == protocol_id)
    if kind:
        q = q.where(Notification.kind == kind)
    rows = list(s.scalars(q.order_by(Notification.created_at.desc(), Notification.id.desc())))
    rows.sort(key=lambda n: n.read_at is not None)
    names = {p.id: p.name for p in s.scalars(select(Protocol).where(Protocol.id.in_({n.protocol_id for n in rows})))}
    return [_note(n, names) for n in rows]


@router.get("/api/notifications/unread-count")
def unread_count(cu: CurrentUser = Depends(require("notifications.view")), s: Session = Depends(db.get_session)):
    rows = s.scalars(_inbox(cu, Notification.id).where(Notification.read_at.is_(None))).all()
    return {"unread": len(rows)}


@router.post("/api/notifications/read-all")
def read_all(protocol_id: int | None = None, cu: CurrentUser = Depends(require("notifications.view")),
             s: Session = Depends(db.get_session)):
    q = _inbox(cu).where(Notification.read_at.is_(None))
    if protocol_id is not None:
        q = q.where(Notification.protocol_id == protocol_id)
    now, count = utcnow(), 0
    for n in s.scalars(q):
        n.read_at, count = now, count + 1
    s.commit()
    return {"read": count}


@router.post("/api/notifications/{notification_id}/read")
def read_one(notification_id: int, cu: CurrentUser = Depends(require("notifications.view")),
             s: Session = Depends(db.get_session)):
    n = s.scalars(_inbox(cu).where(Notification.id == notification_id)).first()
    if n is None:
        raise HTTPException(404, "notification not found")
    if n.read_at is None:
        n.read_at = utcnow()
        s.commit()
    return {"read": 1}
