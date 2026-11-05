from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.schema import DraftECRF
from ecrf.storage import db
from ecrf.storage.models import (
    Observation,
    ObservationHistory,
    Organisation,
    ProtocolSite,
    Study,
    StudyProtocol,
    Subject,
    User,
)

router = APIRouter(prefix="/api/sponsor/ecrf-status", tags=["eCRF status"])


def _iso(value):
    return f"{value.isoformat()}Z" if value else None


def _latest(dates):
    return max((date for date in dates if date is not None), default=None)


def _visit_fields(version):
    visits = {}
    if version is not None:
        for form in DraftECRF.model_validate(version.content).forms:
            for field in form.fields:
                if field.status == "approved":
                    for repeat in range(1, max(1, field.repeats) + 1):
                        visits.setdefault(form.visit, set()).add((field.name, repeat))
    return visits


def _patient_updates(subject, fields_by_visit, observations, histories, actor_sites, version_id):
    site_id = subject.site_org_id
    registered_at = subject.created_at if actor_sites.get(subject.created_by) == site_id else None
    visit_updates = defaultdict(list)
    saved_visits = set()
    for observation in observations:
        if (observation.subject_id != subject.code or observation.ecrf_version_id != version_id
                or (observation.field_name, observation.repeat_num) not in fields_by_visit.get(observation.visit, set())):
            continue
        dates = [change.changed_at for change in histories[observation.id]
                 if actor_sites.get(change.changed_by) == site_id]
        if actor_sites.get(observation.entered_by) == site_id:
            dates.append(observation.entered_at)
        if not dates:
            continue
        visit_updates[observation.visit].extend(dates)
        value = observation.value_num if observation.value_num is not None else observation.value_text
        if value is not None and str(value).strip():
            saved_visits.add(observation.visit)
    if registered_at is None and not visit_updates:
        return None
    latest_entry = _latest(date for dates in visit_updates.values() for date in dates)
    latest_visits = [visit for visit in fields_by_visit
                     if latest_entry is not None and _latest(visit_updates[visit]) == latest_entry]
    return {
        "subject_id": subject.id, "subject_code": subject.code,
        "registered_at": _iso(registered_at),
        "latest_visits": latest_visits,
        "last_hospital_update": _iso(_latest([registered_at, latest_entry])),
        "visits": [{"visit": visit, "has_entries": visit in saved_visits,
                    "last_hospital_update": _iso(_latest(visit_updates[visit]))}
                   for visit in fields_by_visit],
    }


@router.get("")
def overview(current: CurrentUser = Depends(require("stats.view")),
             session: Session = Depends(db.get_session)):
    protocols = session.scalars(scope.visible_protocols(current).order_by("name", "id")).all()
    protocol_ids = [protocol.id for protocol in protocols]
    studies = {study.id: study for study in session.scalars(
        select(Study).where(Study.org_id == current.org.id))}
    study_ids = {assignment.protocol_id: assignment.study_id for assignment in session.scalars(
        select(StudyProtocol).where(StudyProtocol.protocol_id.in_(protocol_ids)))}
    sites = {site.id: site for site in session.scalars(select(Organisation).where(Organisation.type == "site"))}
    actor_sites = {user.email: user.org_id for user in session.scalars(
        select(User).where(User.org_id.in_(sites)))}
    assignments = {(assignment.protocol_id, assignment.site_org_id) for assignment in session.scalars(
        select(ProtocolSite).where(ProtocolSite.protocol_id.in_(protocol_ids)))}
    subjects_by_site = defaultdict(list)
    subjects = session.scalars(select(Subject).where(Subject.protocol_id.in_(protocol_ids))
                              .order_by(Subject.code)).all()
    subject_protocols = {subject.id: subject.protocol_id for subject in subjects}
    for subject in subjects:
        subjects_by_site[(subject.protocol_id, subject.site_org_id)].append(subject)
    observations_by_subject = defaultdict(list)
    for observation in session.scalars(select(Observation).where(Observation.protocol_id.in_(protocol_ids))):
        if subject_protocols.get(observation.subject_ref) == observation.protocol_id:
            observations_by_subject[observation.subject_ref].append(observation)
    histories = defaultdict(list)
    for change in session.scalars(select(ObservationHistory).join(Observation)
                                 .where(Observation.protocol_id.in_(protocol_ids))):
        histories[change.observation_id].append(change)

    hospital_rows = {}
    protocol_options = []
    pairs = assignments | subjects_by_site.keys()
    for protocol in protocols:
        version = db.locked_version(session, protocol.id)
        fields_by_visit = _visit_fields(version)
        study = studies.get(study_ids.get(protocol.id))
        protocol_options.append({"id": protocol.id, "name": protocol.name,
                                 "study_id": study.id if study else None})
        for protocol_id, site_id in sorted(pairs):
            if protocol_id != protocol.id or site_id not in sites:
                continue
            assigned = (protocol.id, site_id) in assignments
            patients = []
            for subject in subjects_by_site[(protocol.id, site_id)]:
                patient = _patient_updates(subject, fields_by_visit, observations_by_subject[subject.id],
                                           histories, actor_sites, version.id if version else None)
                if patient is not None:
                    patients.append(patient)
            if not assigned and not patients:
                continue
            site = sites[site_id]
            hospital = hospital_rows.setdefault(site_id, {
                "site_id": site.id, "site_name": site.name, "site_code": site.code, "protocols": [],
            })
            latest_update = _latest(datetime.fromisoformat(patient["last_hospital_update"].removesuffix("Z"))
                                    for patient in patients if patient["last_hospital_update"])
            hospital["protocols"].append({
                "protocol_id": protocol.id, "protocol_name": protocol.name,
                "study_id": study.id if study else None, "study_name": study.name if study else None,
                "study_code": study.code if study else None, "assigned": assigned,
                "locked_version": version.version if version else None,
                "patient_count": len(patients),
                "patients_with_entries": sum(any(visit["has_entries"] for visit in patient["visits"])
                                             for patient in patients),
                "last_hospital_update": _iso(latest_update),
                "patients": patients,
            })
    return {
        "hospitals": sorted(hospital_rows.values(), key=lambda hospital: (hospital["site_name"].casefold(), hospital["site_id"])),
        "studies": [{"id": study.id, "name": study.name, "code": study.code}
                    for study in sorted(studies.values(), key=lambda study: study.name.casefold())],
        "protocols": protocol_options,
    }
