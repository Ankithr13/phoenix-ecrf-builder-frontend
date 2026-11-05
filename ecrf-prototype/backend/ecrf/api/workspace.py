from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.api.queries import needs_attention
from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import Protocol, Query, Study, StudyProtocol

router = APIRouter(prefix="/api/sponsor/dashboard", tags=["workspace dashboard"])


@router.get("")
def overview(current: CurrentUser = Depends(require("stats.view")),
             session: Session = Depends(db.get_session)):
    studies = session.scalars(select(Study).where(Study.org_id == current.org.id)).all()
    protocols = session.scalars(scope.visible_protocols(current)).all()
    versions = {protocol.id: db.latest_version(session, protocol.id) for protocol in protocols}
    assignments = {assignment.protocol_id: assignment for assignment in session.scalars(
        select(StudyProtocol).join(Protocol, Protocol.id == StudyProtocol.protocol_id)
        .where(Protocol.org_id == current.org.id)).all()}
    queries = session.scalars(select(Query).join(Protocol, Protocol.id == Query.protocol_id)
                              .where(Protocol.org_id == current.org.id)).all()
    study_protocols = {study.id: [] for study in studies}
    unassigned = 0
    for protocol in protocols:
        assignment = assignments.get(protocol.id)
        if assignment and assignment.study_id in study_protocols:
            study_protocols[assignment.study_id].append(protocol)
        else:
            unassigned += 1

    rows = []
    sort_dates = {}
    for study in studies:
        members = study_protocols[study.id]
        locked = sum(1 for protocol in members
                     if versions[protocol.id] and versions[protocol.id].state == "locked")
        pending = sum(1 for protocol in members
                      if versions[protocol.id] and versions[protocol.id].state == "draft")
        unextracted = sum(1 for protocol in members if versions[protocol.id] is None)
        latest_update = None
        for protocol in members:
            version = versions[protocol.id]
            dates = [protocol.uploaded_at, assignments[protocol.id].assigned_at]
            if version:
                dates.append(version.created_at)
                if version.locked_at:
                    dates.append(version.locked_at)
            latest_update = max([latest_update, *dates] if latest_update else dates)
        status = ("needs_review" if pending else "needs_extraction" if unextracted
                  else "forms_locked" if members else "no_protocols")
        sort_dates[study.id] = max(study.created_at, latest_update or study.created_at)
        rows.append({
            "id": study.id, "code": study.code, "name": study.name,
            "protocol_count": len(members), "pending_reviews": pending,
            "locked_protocols": locked, "unextracted_protocols": unextracted,
            "status": status,
            "latest_protocol_update": f"{latest_update.isoformat()}Z" if latest_update else None,
            "created_at": f"{study.created_at.isoformat()}Z",
        })
    rows.sort(key=lambda row: (sort_dates[row["id"]], row["id"]), reverse=True)

    return {
        "counts": {
            "studies": len(studies), "protocols": len(protocols),
            "pending_reviews": sum(1 for version in versions.values()
                                   if version and version.state == "draft"),
            "queries_for_me": sum(1 for query in queries if needs_attention(query, current.org.type)),
            "unassigned_protocols": unassigned,
            "unextracted_protocols": sum(1 for version in versions.values() if version is None),
            "locked_protocols": sum(1 for version in versions.values()
                                    if version and version.state == "locked"),
        },
        "studies": rows,
    }
