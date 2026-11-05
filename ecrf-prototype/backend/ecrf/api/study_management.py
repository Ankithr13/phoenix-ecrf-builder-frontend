import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.storage import db
from ecrf.storage.models import Study, StudyProtocol

router = APIRouter(prefix="/api/sponsor/studies", tags=["study management"])


class StudyCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)

    @field_validator("code")
    @classmethod
    def clean_code(cls, value: str) -> str:
        code = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]{0,63}", code):
            raise ValueError("Use letters, numbers, hyphens, periods, underscores or slashes for the study ID")
        return code

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise ValueError("A study name is required")
        return name


def _study_row(session: Session, study: Study) -> dict:
    count = session.scalar(select(func.count(StudyProtocol.protocol_id)).where(
        StudyProtocol.study_id == study.id)) or 0
    return {"id": study.id, "code": study.code, "name": study.name,
            "protocol_count": count, "created_at": study.created_at.isoformat()}


@router.get("")
def list_studies(current: CurrentUser = Depends(require("study.manage")),
                 session: Session = Depends(db.get_session)):
    studies = session.scalars(select(Study).where(Study.org_id == current.org.id)
                              .order_by(func.lower(Study.name), Study.id)).all()
    return [_study_row(session, study) for study in studies]


@router.post("", status_code=201)
def create_study(body: StudyCreate, current: CurrentUser = Depends(require("study.manage")),
                 session: Session = Depends(db.get_session)):
    study = Study(org_id=current.org.id, code=body.code, name=body.name,
                  created_by=current.user.email)
    session.add(study)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(409, "That study ID already exists in your organisation") from error
    return _study_row(session, study)


@router.get("/{study_id}")
def get_study(study_id: int, current: CurrentUser = Depends(require("study.manage")),
              session: Session = Depends(db.get_session)):
    return _study_row(session, scope.study_or_404(session, current, study_id))


class StudyAssignment(BaseModel):
    study_id: int | None = Field(..., gt=0)


assignment_router = APIRouter(prefix="/api/protocols", tags=["study management"])


@assignment_router.put("/{protocol_id}/study")
def assign_protocol(protocol_id: int, body: StudyAssignment,
                    current: CurrentUser = Depends(require("study.manage")),
                    session: Session = Depends(db.get_session)):
    protocol = scope.protocol_or_404(session, current, protocol_id)
    if body.study_id is not None:
        scope.study_or_404(session, current, body.study_id)
    db.assign_study(session, protocol.id, body.study_id, current.user.email)
    session.commit()
    return {"protocol_id": protocol.id, "study_id": body.study_id}
