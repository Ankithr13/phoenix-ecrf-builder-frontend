import hashlib
import json

from sqlalchemy import select

from ecrf.schema import DraftECRF
from ecrf.storage import db
from ecrf.storage.models import HospitalSubmission, Observation, Subject


def hospital_snapshot(session, protocol_id, site_id, version):
    subjects = session.scalars(select(Subject).where(Subject.protocol_id == protocol_id,
                                                    Subject.site_org_id == site_id).order_by(Subject.id)).all()
    subjects_by_id = {subject.id: subject for subject in subjects}
    fields = set()
    if version:
        for form in DraftECRF.model_validate(version.content).forms:
            for field in form.fields:
                if field.status == "approved":
                    fields.update((form.visit, field.name, repeat) for repeat in range(1, max(1, field.repeats) + 1))
    readings = session.scalars(select(Observation).where(Observation.protocol_id == protocol_id,
                                                        Observation.subject_ref.in_(subjects_by_id))
                               .order_by(Observation.id)).all()
    entries = [reading for reading in readings
               if version and reading.ecrf_version_id == version.id
               and reading.subject_id == subjects_by_id[reading.subject_ref].code
               and (reading.visit, reading.field_name, reading.repeat_num) in fields]
    payload = {
        "version": version.id if version else None,
        "patients": [[subject.id, subject.code, subject.initials, subject.birth_year, subject.sex,
                      subject.enrolled_on, subject.note] for subject in subjects],
        "entries": [[reading.subject_ref, reading.visit, reading.field_name, reading.repeat_num,
                     reading.value_num, reading.value_text] for reading in entries],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    has_entries = any(reading.value_num is not None or bool((reading.value_text or "").strip()) for reading in entries)
    return digest, len(subjects), has_entries


def submission_status(session, protocol_id, site_id, version=None):
    version = version or db.locked_version(session, protocol_id)
    digest, patients, has_entries = hospital_snapshot(session, protocol_id, site_id, version)
    previous = session.scalar(select(HospitalSubmission).where(
        HospitalSubmission.protocol_id == protocol_id, HospitalSubmission.site_org_id == site_id)
        .order_by((HospitalSubmission.snapshot_hash == digest).desc(), HospitalSubmission.id.desc()).limit(1))
    return {
        "state": "not_submitted" if previous is None else "submitted" if previous.snapshot_hash == digest else "changed",
        "submission_id": previous.id if previous else None,
        "submitted_at": f"{previous.submitted_at.isoformat()}Z" if previous else None,
        "submitted_by": previous.submitted_by if previous else None,
        "patient_count": patients, "can_submit": bool(version and patients and has_entries),
    }
