"""What a signed-in user may see. Every list and every lookup goes through
here, so the rule lives in one place:

  sponsor   protocols that belong to its organisation; every site's data,
            except a monitor, who sees only the sites assigned to them
  site      protocols assigned to it whose form is locked; its own
            subjects and their data only

A row outside the scope is reported as 404."""

from fastapi import HTTPException
from sqlalchemy import Select, exists, select
from sqlalchemy.orm import Session

from ecrf.auth.permissions import CurrentUser
from ecrf.storage.models import ECRFVersion, Observation, Protocol, ProtocolSite, Subject


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
    if cu.site_ids is not None:
        q = q.where(Subject.site_org_id.in_(cu.site_ids))
    return q


def subject_or_404(s: Session, cu: CurrentUser, protocol_id: int, code: str) -> Subject:
    subj = s.scalars(visible_subjects(cu, protocol_id).where(Subject.code == code)).first()
    if subj is None:
        raise HTTPException(404, "subject not found")
    return subj


def visible_observations(cu: CurrentUser, protocol_id: int) -> Select:
    q = select(Observation).where(Observation.protocol_id == protocol_id)
    # A draft is still the site's to change. The sponsor sees it once submitted.
    if cu.org.type == "sponsor":
        q = q.where(Observation.status != "draft")
    if cu.site_ids is not None:
        q = q.join(Subject, Subject.id == Observation.subject_ref).where(Subject.site_org_id.in_(cu.site_ids))
    return q


def check_study_open(p: Protocol) -> None:
    """After the study lock, every write to its data is refused."""
    if p.study_locked_at is not None:
        raise HTTPException(409, "This study is locked; its data can no longer change")


def require_sponsor_side(cu: CurrentUser) -> None:
    """Screens that describe the whole study, not one site's part of it."""
    if cu.org.type != "sponsor":
        raise HTTPException(403, f"Your role ({cu.role}) cannot do this")


def require_site_side(cu: CurrentUser) -> None:
    if cu.org.type != "site":
        raise HTTPException(403, f"Your role ({cu.role}) cannot do this")
