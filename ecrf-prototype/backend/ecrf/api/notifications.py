from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query as QueryParam
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import Notification, NotificationRead, Organisation, Protocol

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _visible(current):
    return (select(Notification).join(Protocol, Protocol.id == Notification.protocol_id)
            .where(Notification.org_id == current.org.id, Protocol.org_id == current.org.id))


def _mark_read(session, current, notification_id):
    key = {"notification_id": notification_id, "user_id": current.user.id}
    if session.get(NotificationRead, key) is None:
        try:
            with session.begin_nested():
                session.add(NotificationRead(**key))
                session.flush()
        except IntegrityError:
            if session.get(NotificationRead, key) is None:
                raise


@router.get("")
def list_notifications(before_id: int | None = QueryParam(default=None, ge=1),
                       limit: int = QueryParam(default=20, ge=1, le=50), unread_only: bool = False,
                       current: CurrentUser = Depends(require("notifications.view")),
                       session: Session = Depends(db.get_session)):
    read_join = and_(NotificationRead.notification_id == Notification.id, NotificationRead.user_id == current.user.id)
    visible = _visible(current)
    unread = visible.outerjoin(NotificationRead, read_join).where(NotificationRead.notification_id.is_(None))
    unread_count = session.scalar(select(func.count()).select_from(unread.subquery())) or 0
    query = (visible.add_columns(NotificationRead.read_at, Protocol.name, Organisation.name)
             .join(Organisation, Organisation.id == Notification.site_org_id).outerjoin(NotificationRead, read_join))
    if before_id is not None:
        query = query.where(Notification.id < before_id)
    if unread_only:
        query = query.where(NotificationRead.notification_id.is_(None))
    records = session.execute(query.order_by(Notification.id.desc()).limit(limit + 1)).all()
    items = []
    for notification, read_at, protocol_name, hospital_name in records[:limit]:
        query_alert = notification.kind == "hospital_query"
        items.append({
            "id": notification.id, "kind": notification.kind,
            "title": "New hospital query" if query_alert else "Hospital submitted eCRF",
            "hospital_name": hospital_name, "protocol_name": protocol_name,
            "protocol_id": notification.protocol_id, "site_id": notification.site_org_id,
            "query_id": notification.query_id,
            "created_at": f"{notification.created_at.isoformat()}Z",
            "read_at": f"{read_at.isoformat()}Z" if read_at else None,
            "destination": (f"/sponsor/queries?query={notification.query_id}" if query_alert else
                            f"/sponsor/ecrf-status?hospital={notification.site_org_id}&protocol={notification.protocol_id}"),
        })
    return {"items": items, "unread_count": unread_count,
            "next_before_id": items[-1]["id"] if len(records) > limit else None}


class ReadAllRequest(BaseModel):
    through_id: int = Field(ge=1)


@router.post("/read-all")
def read_all(body: ReadAllRequest, current: CurrentUser = Depends(require("notifications.view")),
             session: Session = Depends(db.get_session)):
    notifications = session.scalars(_visible(current).where(Notification.id <= body.through_id)).all()
    for notification in notifications:
        _mark_read(session, current, notification.id)
    session.commit()
    return {"read": True}


@router.post("/{notification_id}/read")
def read_one(notification_id: int, current: CurrentUser = Depends(require("notifications.view")),
             session: Session = Depends(db.get_session)):
    notification = session.scalar(_visible(current).where(Notification.id == notification_id))
    if notification is None:
        raise HTTPException(404, "notification not found")
    _mark_read(session, current, notification.id)
    session.commit()
    return {"read": True}
