from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import HospitalSubmission, Notification
from ecrf.submissions import hospital_snapshot, submission_status

router = APIRouter(prefix="/api/studies", tags=["hospital submissions"])


class SubmissionRequest(BaseModel):
    confirmed: bool = False


@router.get("/{protocol_id}/submission")
def status(protocol_id: int, current: CurrentUser = Depends(require("ecrf.submit")),
           session: Session = Depends(db.get_session)):
    scope.protocol_or_404(session, current, protocol_id)
    return submission_status(session, protocol_id, current.org.id)


@router.post("/{protocol_id}/submission")
def submit(protocol_id: int, body: SubmissionRequest,
           current: CurrentUser = Depends(require("ecrf.submit")),
           session: Session = Depends(db.get_session)):
    protocol = scope.protocol_or_404(session, current, protocol_id)
    if not body.confirmed:
        raise HTTPException(422, "Confirm that your hospital's entire assigned eCRF is ready for sponsor review")
    version = db.locked_version(session, protocol_id)
    digest, patients, has_entries = hospital_snapshot(session, protocol_id, current.org.id, version)
    if not version or not patients or not has_entries:
        raise HTTPException(409, "Register patients and save data against the locked eCRF before submitting")
    existing = session.scalar(select(HospitalSubmission).where(
        HospitalSubmission.protocol_id == protocol_id, HospitalSubmission.site_org_id == current.org.id,
        HospitalSubmission.snapshot_hash == digest))
    if existing is None:
        try:
            with session.begin_nested():
                submission = HospitalSubmission(protocol_id=protocol_id, site_org_id=current.org.id,
                                                ecrf_version_id=version.id, snapshot_hash=digest,
                                                patient_count=patients, submitted_by=current.user.email)
                session.add(submission)
                session.flush()
                session.add(Notification(org_id=protocol.org_id, protocol_id=protocol.id,
                                         site_org_id=current.org.id, kind="ecrf_submitted",
                                         submission_id=submission.id, event_key=f"submission:{submission.id}"))
                session.flush()
        except IntegrityError:
            existing = session.scalar(select(HospitalSubmission).where(
                HospitalSubmission.protocol_id == protocol_id, HospitalSubmission.site_org_id == current.org.id,
                HospitalSubmission.snapshot_hash == digest))
            if existing is None:
                raise
    session.commit()
    return submission_status(session, protocol_id, current.org.id, version)
