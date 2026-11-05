"""What a signed-in user may see. Every list and every lookup goes through
here, so the rule lives in one place:

  sponsor   protocols that belong to its organisation; every site's data
  site      protocols assigned to it whose form is locked; its own
            subjects and their data only

A row outside the scope is reported as 404."""

from fastapi import HTTPException
from sqlalchemy import Select, exists, select
from sqlalchemy.orm import Session

from ecrf.auth.permissions import CurrentUser
from ecrf.storage.models import ECRFVersion, Observation, Protocol, ProtocolSite, Study, Subject


def study_or_404(session: Session, current: CurrentUser, study_id: int) -> Study:
    study = session.scalar(select(Study).where(Study.id == study_id, Study.org_id == current.org.id))
    if study is None:
        raise HTTPException(404, "study not found")
    return study


def _locked() -> Select:
    return exists(select(ECRFVersion.id).where(
        ECRFVersion.protocol_id == Protocol.id, ECRFVersion.state == "locked"))


def visible_protocols(cu: CurrentUser) -> Select:
    if cu.org.type == "sponsor":
        return select(Protocol).where(Protocol.org_id == cu.org.id)
    return (select(Protocol)
            .join(ProtocolSite, ProtocolSite.protocol_id == Protocol.id)
            .where(ProtocolSite.site_org_id == cu.org.id, _locked()))


def protocol_or_404(s: Session, cu: CurrentUser, protocol_id: int) -> Protocol:
    p = s.scalars(visible_protocols(cu).where(Protocol.id == protocol_id)).first()
    if p is None:
        raise HTTPException(404, "protocol not found")
    return p


def visible_subjects(cu: CurrentUser, protocol_id: int) -> Select:
    q = select(Subject).where(Subject.protocol_id == protocol_id)
    if cu.org.type == "site":
        q = q.where(Subject.site_org_id == cu.org.id)
    return q


def subject_or_404(s: Session, cu: CurrentUser, protocol_id: int, code: str) -> Subject:
    subj = s.scalars(visible_subjects(cu, protocol_id).where(Subject.code == code)).first()
    if subj is None:
        raise HTTPException(404, "subject not found")
    return subj


def visible_observations(cu: CurrentUser, protocol_id: int) -> Select:
    q = select(Observation).where(Observation.protocol_id == protocol_id)
    if cu.org.type == "site":
        q = q.join(Subject, Subject.id == Observation.subject_ref).where(Subject.site_org_id == cu.org.id)
    return q
