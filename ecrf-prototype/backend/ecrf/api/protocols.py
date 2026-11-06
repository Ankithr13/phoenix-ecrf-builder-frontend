"""Protocol upload, extraction, draft review, approval.

Every route needs a signed-in user. What they may do comes from the one
permission table; what they may see comes from the scope helpers."""

import re
import shutil
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf import cdash, ingest, pipeline
from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.config import config
from ecrf.extract import get_extractor
from ecrf.extract.base import Usage
from ecrf.schema import DraftECRF, ExtractionPlan, FieldType, Status
from ecrf.storage import db
from ecrf.storage.models import ECRFVersion, Protocol, StudyProtocol, utcnow

router = APIRouter(prefix="/api/protocols", tags=["protocols"])

UPLOAD_DIR = config.upload_dir
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _doc_from_protocol(p: Protocol) -> ingest.Document:
    """Rebuild a Document from stored text + sections, no re-parse.

    Each section's body is sliced back out of the stored normalised text
    using the offsets recorded at upload. Leaving it empty (as an earlier
    version did) silently breaks ECRF_CONTEXT=sections: section selection
    scores sections by their body, so with empty bodies it either picks a
    section on its title alone and sends the model a heading with no
    content, or finds nothing and falls back to the whole document. Both
    look like success from outside.
    """
    doc = ingest.Document(text=p.normalised, pages=p.pages, hash=p.text_hash,
                          tokens_estimate=p.tokens_estimate)
    doc.sections = [ingest.Section(s["number"], s["title"], s["page"],
                                   p.normalised[s["start"]:s["end"]],
                                   s["start"], s["end"]) for s in p.sections]
    return doc


# ----------------------------------------------------------------- list

@router.get("")
def list_protocols(study_id: int | None = None, unassigned: bool = False,
                   cu: CurrentUser = Depends(require("protocol.view")),
                   s: Session = Depends(db.get_session)):
    query = scope.visible_protocols(cu)
    if study_id is not None:
        scope.study_or_404(s, cu, study_id)
        if unassigned:
            raise HTTPException(422, "Choose a study or unassigned protocols, not both")
        query = query.where(Protocol.id.in_(select(StudyProtocol.protocol_id).where(
            StudyProtocol.study_id == study_id)))
    elif unassigned:
        query = query.where(~Protocol.id.in_(select(StudyProtocol.protocol_id)))
    rows = s.scalars(query.order_by(Protocol.uploaded_at.desc())).all()
    out = []
    for p in rows:
        v = db.latest_version(s, p.id)
        study = db.protocol_study(s, p.id)
        out.append({
            "id": p.id, "name": p.name, "filename": p.filename, "pages": p.pages,
            "tokens_estimate": p.tokens_estimate, "uploaded_by": p.uploaded_by,
            "uploaded_at": p.uploaded_at.isoformat(),
            "latest_version": v.version if v else None,
            "state": v.state if v else None,
            "review_blockers": _lock_blockers(v.content) if v else None,
            "summary": (v.content.get("summary") if v else None),
            "plan": _plan_response(p) if p.extraction_plan else None,
            "study_id": study.id if study else None,
            "study_name": study.name if study else None,
            "study_code": study.code if study else None,
        })
    return out


# --------------------------------------------------------------- upload

@router.post("/upload")
async def upload(file: UploadFile = File(...), study_id: int | None = Form(None, gt=0),
                 cu: CurrentUser = Depends(require("protocol.upload")),
                 s: Session = Depends(db.get_session)):
    if study_id is not None:
        scope.study_or_404(s, cu, study_id)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF protocols are supported in the prototype")
    dest = UPLOAD_DIR / f"{uuid4().hex}_{Path(file.filename).name}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        doc = ingest.load(str(dest))
    except ingest.ScannedPDFError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(e)) from e
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    # The same document uploaded twice must not become two protocols that
    # drift apart under review. Match on the hash of the normalised text, so
    # a renamed file still counts as the same protocol.
    existing = s.scalars(select(Protocol).where(
        Protocol.text_hash == doc.hash, Protocol.org_id == cu.org.id)).first()
    if existing:
        dest.unlink(missing_ok=True)
        _assign_uploaded_study(s, cu, existing, study_id)
        s.commit()
        return {"id": existing.id, "name": existing.name, "pages": existing.pages,
                "tokens_estimate": existing.tokens_estimate, "already_loaded": True,
                "study_id": _assigned_study_id(s, existing.id)}

    name = Path(file.filename).stem.replace("_", " ")
    p = Protocol(
        name=name, filename=dest.name, text_hash=doc.hash, normalised=doc.text,
        sections=[{"number": x.number, "title": x.title, "page": x.page_start,
                   "start": x.start, "end": x.end} for x in doc.sections],
        pages=doc.pages, tokens_estimate=doc.tokens_estimate,
        uploaded_by=cu.user.email, org_id=cu.org.id,
    )
    s.add(p)
    s.flush()
    _assign_uploaded_study(s, cu, p, study_id)
    s.commit()
    return {"id": p.id, "name": p.name, "pages": p.pages,
            "tokens_estimate": p.tokens_estimate, "sections": len(doc.sections),
            "tables": len(doc.tables), "study_id": study_id}


def _assigned_study_id(session: Session, protocol_id: int) -> int | None:
    assignment = session.get(StudyProtocol, protocol_id)
    return assignment.study_id if assignment else None


def _assign_uploaded_study(session: Session, current: CurrentUser,
                           protocol: Protocol, study_id: int | None) -> None:
    if study_id is None:
        return
    assigned_id = _assigned_study_id(session, protocol.id)
    if assigned_id is not None and assigned_id != study_id:
        raise HTTPException(409, "This protocol already belongs to another study. Change its assignment from the Protocols page instead.")
    db.assign_study(session, protocol.id, study_id, current.user.email)


@router.post("/sample")
def load_sample(study_id: int | None = None,
                cu: CurrentUser = Depends(require("protocol.upload")),
                s: Session = Depends(db.get_session)):
    """Load the bundled synthetic protocol without a file picker."""
    if study_id is not None:
        scope.study_or_404(s, cu, study_id)
    src = config.data_dir / "sample" / "PHX-401-201_protocol.pdf"
    if not src.exists():
        raise HTTPException(500, "sample protocol missing; run data/sample/make_sample_protocol.py")
    doc = ingest.load(str(src))
    existing = s.scalars(select(Protocol).where(
        Protocol.text_hash == doc.hash, Protocol.org_id == cu.org.id)).first()
    if existing:
        _assign_uploaded_study(s, cu, existing, study_id)
        s.commit()
        return {"id": existing.id, "name": existing.name, "already_loaded": True,
                "study_id": _assigned_study_id(s, existing.id)}
    p = Protocol(
        name="PHX-401-201 (synthetic sample)", filename=src.name, text_hash=doc.hash,
        normalised=doc.text,
        sections=[{"number": x.number, "title": x.title, "page": x.page_start,
                   "start": x.start, "end": x.end} for x in doc.sections],
        pages=doc.pages, tokens_estimate=doc.tokens_estimate,
        uploaded_by=cu.user.email, org_id=cu.org.id,
    )
    s.add(p)
    s.flush()
    _assign_uploaded_study(s, cu, p, study_id)
    s.commit()
    return {"id": p.id, "name": p.name, "already_loaded": False, "study_id": study_id}


# ------------------------------------------------------------- extract

LOCKED = ("Form is locked. Changing a locked form is out of scope for this sprint; "
          "a later sprint will add versioned amendments.")


def _lock_blockers(content: dict) -> dict[str, int]:
    counts = {"draft": 0, "flagged": 0}
    for form in content.get("forms", []):
        for f in form.get("fields", []):
            if f.get("status") in counts:
                counts[f["status"]] += 1
    return counts


def _lock_warnings(content: dict) -> list[dict]:
    """Approved fields a site cannot answer well. None of these block the
    lock, because each can be a deliberate choice, but the reviewer should
    see them before freezing the form."""
    choice_no_list, num_no_range, num_no_unit = [], [], []
    for form in content.get("forms", []):
        for f in form.get("fields", []):
            if f.get("status") != "approved":
                continue
            tag = f"{form['visit']}: {f['name']}"
            if f.get("type") == "choice" and not f.get("choices"):
                choice_no_list.append(tag)
            if f.get("type") in ("integer", "decimal"):
                if f.get("min") is None or f.get("max") is None:
                    num_no_range.append(tag)
                if not f.get("unit"):
                    num_no_unit.append(tag)
    out = []
    if choice_no_list:
        out.append({"kind": "choice_without_choices", "count": len(choice_no_list), "fields": choice_no_list,
                    "text": "choice fields with no answer list; the site will get a free-text box"})
    if num_no_range:
        out.append({"kind": "numeric_without_range", "count": len(num_no_range), "fields": num_no_range,
                    "text": "numeric fields with no min or max; any number will be accepted"})
    if num_no_unit:
        out.append({"kind": "numeric_without_unit", "count": len(num_no_unit), "fields": num_no_unit,
                    "text": "numeric fields with no unit; sites may record in different units"})
    return out


def _reviewed(v: ECRFVersion) -> bool:
    """Has a human touched this version? A review always writes a version
    whose note is not the extraction note, and approval is only ever set by
    a person."""
    if not (v.note or "").startswith("initial extraction"):
        return True
    return any(f.get("status") == "approved"
               for form in v.content.get("forms", []) for f in form.get("fields", []))


def _guard_extract(s: Session, protocol_id: int, force: bool) -> None:
    latest = db.latest_version(s, protocol_id)
    if latest and latest.state == "locked":
        raise HTTPException(409, LOCKED)
    if latest and not force and _reviewed(latest):
        # Extraction writes a fresh draft with every status reset, so running
        # it on a reviewed protocol throws the review away. That happened
        # once for real before this check existed.
        raise HTTPException(
            409, f"Version {latest.version} of this protocol has been reviewed. Extracting "
                 f"again would start a new draft and none of the approvals or edits would "
                 f"carry over. Add ?force=true to do it anyway; the reviewed version is "
                 f"kept and a new version is created.")


def _plan_response(p: Protocol) -> dict:
    plan = p.extraction_plan or {}
    return {"visits": plan.get("visits", []), "forms": plan.get("forms", []),
            "confirmed": bool(plan.get("confirmed")), "usage": plan.get("usage"),
            "strategy": config.extract_strategy,
            "estimated_calls": pipeline.estimated_calls(
                ExtractionPlan(visits=plan.get("visits", []), forms=plan.get("forms", []))) if plan else 0}


@router.post("/{protocol_id}/extract")
def extract(protocol_id: int, backend: str | None = None, force: bool = False,
            cu: CurrentUser = Depends(require("protocol.extract")),
            s: Session = Depends(db.get_session)):
    """Both passes in one go, no human step. Kept for the mock and tests;
    the two-step route below is what the UI uses."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    _guard_extract(s, protocol_id, force)
    doc = _doc_from_protocol(p)
    try:
        draft = pipeline.run(str(UPLOAD_DIR / p.filename), protocol_id, backend=backend,
                             doc=doc, force=force)
    except Exception as e:  # surface provider errors plainly
        raise HTTPException(502, f"extraction failed: {type(e).__name__}: {e}") from e
    v = db.save_version(s, p, draft.model_dump(), cu.user.email, note="initial extraction")
    s.commit()
    return {"version": v.version, "summary": draft.summary}


# ------------------------------------------------- two-step extraction

@router.post("/{protocol_id}/extract/visits")
def extract_visits(protocol_id: int, backend: str | None = None, force: bool = False,
                   cu: CurrentUser = Depends(require("protocol.extract")),
                   s: Session = Depends(db.get_session)):
    """Pass one only. The proposed visit list is stored on the protocol for
    a person to correct before any per-visit call is paid for."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    _guard_extract(s, protocol_id, force)
    doc = _doc_from_protocol(p)
    ex = get_extractor(backend)
    ex.begin_run(doc.hash, force=force)
    try:
        plan = pipeline.plan(doc, ex)
    except Exception as e:
        raise HTTPException(502, f"extraction failed: {type(e).__name__}: {e}") from e
    p.extraction_plan = {**plan.model_dump(), "confirmed": False, "usage": ex.usage.summary(),
                         "backend": ex.name, "model": ex.model}
    s.commit()
    return _plan_response(p)


class VisitsRequest(BaseModel):
    visits: list[str]


@router.get("/{protocol_id}/visits")
def get_visits(protocol_id: int, cu: CurrentUser = Depends(require("protocol.view")),
               s: Session = Depends(db.get_session)):
    return _plan_response(scope.protocol_or_404(s, cu, protocol_id))


@router.put("/{protocol_id}/visits")
def put_visits(protocol_id: int, body: VisitsRequest,
               cu: CurrentUser = Depends(require("protocol.extract")),
               s: Session = Depends(db.get_session)):
    """Save the corrected visit list. Forms keep only the visits that still
    exist; a form left with none is dropped."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    _guard_extract(s, protocol_id, force=True)
    visits = [v.strip() for v in body.visits if v.strip()]
    if len(set(visits)) != len(visits):
        raise HTTPException(422, "visit names must be unique")
    if not visits:
        raise HTTPException(422, "at least one visit is needed")
    plan = dict(p.extraction_plan or {})
    forms = []
    for f in plan.get("forms", []):
        kept = [v for v in f.get("visits", []) if v in visits]
        if kept:
            forms.append({"name": f["name"], "visits": kept})
    plan.update({"visits": visits, "forms": forms, "confirmed": True})
    p.extraction_plan = plan
    s.commit()
    return _plan_response(p)


@router.post("/{protocol_id}/extract/fields")
def extract_fields(protocol_id: int, backend: str | None = None, force: bool = False,
                   cu: CurrentUser = Depends(require("protocol.extract")),
                   s: Session = Depends(db.get_session)):
    """Pass two on the confirmed visit list, then verification, enrichment
    and a new version. Usage from pass one is folded into the summary so
    calls = visits + 1 still reads correctly."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    _guard_extract(s, protocol_id, force)
    if not p.extraction_plan or not p.extraction_plan.get("visits"):
        raise HTTPException(409, "Extract the visits first")
    plan = ExtractionPlan(visits=p.extraction_plan["visits"], forms=p.extraction_plan.get("forms", []))
    doc = _doc_from_protocol(p)
    ex = get_extractor(backend)
    ex.begin_run(doc.hash, force=force)
    pass_one = Usage.from_summary(p.extraction_plan.get("usage") or {})
    try:
        draft = pipeline.run_fields(doc, plan, ex, protocol_id, pass_one_usage=pass_one)
    except Exception as e:
        raise HTTPException(502, f"extraction failed: {type(e).__name__}: {e}") from e
    v = db.save_version(s, p, draft.model_dump(), cu.user.email, note="initial extraction")
    s.commit()
    return {"version": v.version, "summary": draft.summary}


# --------------------------------------------------------------- draft

@router.get("/{protocol_id}/draft")
def get_draft(protocol_id: int,
              cu: CurrentUser = Depends(require("protocol.view", "study.view")),
              s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)
    v = db.latest_version(s, protocol_id)
    if not v:
        return {"protocol": {"id": p.id, "name": p.name}, "version": None, "draft": None,
                "plan": _plan_response(p) if p.extraction_plan else None}
    draft = DraftECRF.model_validate(v.content)
    sugg = {f.visit: cdash.suggestions(f) for f in draft.forms}
    return {
        "protocol": {"id": p.id, "name": p.name, "pages": p.pages,
                     "tokens_estimate": p.tokens_estimate, "hash": p.text_hash[:12]},
        "version": v.version, "created_by": v.created_by, "created_at": v.created_at.isoformat(),
        "note": v.note, "draft": draft.model_dump(), "library_suggestions": sugg,
        "state": v.state, "locked_by": v.locked_by,
        "locked_at": v.locked_at.isoformat() if v.locked_at else None,
        "lock_blockers": _lock_blockers(v.content),
        "lock_warnings": _lock_warnings(v.content),
    }


@router.get("/{protocol_id}/versions")
def versions(protocol_id: int,
             cu: CurrentUser = Depends(require("protocol.view", "study.view")),
             s: Session = Depends(db.get_session)):
    scope.protocol_or_404(s, cu, protocol_id)
    rows = s.scalars(select(ECRFVersion).where(ECRFVersion.protocol_id == protocol_id)
                     .order_by(ECRFVersion.version)).all()
    return [{"version": r.version, "created_by": r.created_by,
             "created_at": r.created_at.isoformat(), "note": r.note,
             "summary": r.content.get("summary")} for r in rows]


@router.get("/{protocol_id}/section/{number}")
def section_text(protocol_id: int, number: str,
                 cu: CurrentUser = Depends(require("protocol.view", "study.view")),
                 s: Session = Depends(db.get_session)):
    """Lets the reviewer read the cited section without opening the PDF.

    Three ways to find it, because models cite sections three ways: the
    number ("7.3.2"), the heading ("Schedule of Events"), or a phrase that
    is not a heading at all. Section detection also misses headings on
    some protocols, so a title or phrase falls back to a text search and
    returns the passage around the first hit, labelled as such."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    want = number.strip()
    for sec in p.sections:
        if sec["number"] == want:
            return {"number": want, "title": sec["title"], "page": sec["page"],
                    "text": p.normalised[sec["start"]:sec["end"]], "located_by": "number"}
    low = want.lower()
    if len(low) >= 4:
        for sec in p.sections:
            title = (sec.get("title") or "").lower()
            if title and (low in title or title in low):
                return {"number": sec["number"], "title": sec["title"], "page": sec["page"],
                        "text": p.normalised[sec["start"]:sec["end"]], "located_by": "title"}
        # Whitespace-insensitive: the protocol breaks lines where the model's
        # citation has a space.
        pat = re.compile(r"\s+".join(re.escape(w) for w in low.split()), re.IGNORECASE)
        m = pat.search(p.normalised)
        if m:
            i = m.start()
            start, end = max(0, i - 200), min(len(p.normalised), i + 1800)
            return {"number": want, "title": want, "page": None,
                    "text": p.normalised[start:end], "located_by": "text"}
    raise HTTPException(404, "section not found")


# ------------------------------------------------------------- approve

class FieldChange(BaseModel):
    """One reviewer edit. `name` identifies the field; everything else is
    optional and only what is sent is changed. Renaming goes through
    `new_name` so the identifier and the edit cannot be confused."""
    visit: str
    name: str
    status: Status | None = None
    new_name: str | None = None
    type: FieldType | None = None
    unit: str | None = None
    min: float | None = None
    max: float | None = None
    required: bool | None = None
    repeats: int | None = None
    choices: list[str] | None = None
    reviewer_note: str | None = None


# Reviewer-editable attributes, applied in this order.
_EDITABLE = ("type", "unit", "min", "max", "required", "repeats", "choices")


class ReviewRequest(BaseModel):
    changes: list[FieldChange]
    note: str | None = None
    action: Literal["save", "approve_all_remaining", "approve_suggested"] = "save"
    # approve_suggested takes library values by default; guessed ranges only
    # when the reviewer asks for them explicitly.
    include_guesses: bool = False


@router.post("/{protocol_id}/review")
def review(protocol_id: int, body: ReviewRequest,
           cu: CurrentUser = Depends(require("form.edit")),
           s: Session = Depends(db.get_session)):
    """Apply reviewer edits and write a NEW version. Never updates in place."""
    p = scope.protocol_or_404(s, cu, protocol_id)
    v = db.latest_version(s, protocol_id)
    if not v:
        raise HTTPException(404, "no draft to review")
    if v.state == "locked":
        raise HTTPException(409, LOCKED)
    draft = DraftECRF.model_validate(v.content)

    by_key = {(f.visit, fld.name): fld for f in draft.forms for fld in f.fields}
    applied = 0
    for ch in body.changes:
        fld = by_key.get((ch.visit, ch.name))
        if not fld:
            continue
        if ch.repeats is not None and ch.repeats < 1:
            raise HTTPException(422, f"{ch.name}: repeats must be at least 1")
        edited = []
        for attr in _EDITABLE:
            val = getattr(ch, attr)
            if val is not None:
                if attr == "unit" and not val.strip():
                    val = None
                if attr == "choices":
                    val = [c.strip() for c in val if c.strip()] or None
                setattr(fld, attr, val)
                edited.append(attr)
        if fld.min is not None and fld.max is not None and fld.min > fld.max:
            raise HTTPException(422, f"{ch.name}: min {fld.min} is above max {fld.max}")
        if fld.type == "choice" and not fld.choices:
            raise HTTPException(422, f"{ch.name}: a choice field needs at least one choice")
        new_name = (ch.new_name or "").strip()
        if new_name and new_name != fld.name:
            if (ch.visit, new_name) in by_key:
                raise HTTPException(422, f"{ch.visit} already has a field called {new_name}")
            del by_key[(ch.visit, fld.name)]
            fld.name = new_name
            by_key[(ch.visit, new_name)] = fld
        # A reviewer's value replaces a suggestion, so the label comes off.
        if edited and fld.suggested:
            fld.suggested = [a for a in fld.suggested if a not in edited]
            if not fld.suggested:
                fld.suggested_from = None
        if ch.status is not None:
            fld.status = ch.status
        if ch.status == "approved":
            fld.issue = "none"
        applied += 1

    if body.action == "approve_all_remaining":
        for fld in by_key.values():
            if fld.status == "draft":
                fld.status = "approved"
    if body.action == "approve_suggested":
        # Flagged only because the protocol was silent on something the
        # library has a standard answer for. One click is still a sign-off:
        # the reviewer chose to accept the library's values.
        for fld in by_key.values():
            if fld.status != "flagged" or fld.issue != "missing" or not fld.suggested:
                continue
            if fld.suggested_from == "heuristic" and not body.include_guesses:
                continue
            fld.status, fld.issue = "approved", "none"
            applied += 1

    draft.version = v.version + 1
    nv = db.save_version(s, p, draft.model_dump(), cu.user.email,
                         note=body.note or f"review: {applied} change(s)")
    s.commit()
    return {"version": nv.version, "applied": applied}


# ---------------------------------------------------------------- lock

@router.post("/{protocol_id}/lock")
def lock(protocol_id: int, cu: CurrentUser = Depends(require("form.lock")),
         s: Session = Depends(db.get_session)):
    """Freeze the latest version. Allowed only once every field has been
    approved or rejected; sites only ever see a locked form."""
    scope.protocol_or_404(s, cu, protocol_id)
    v = db.latest_version(s, protocol_id)
    if not v:
        raise HTTPException(404, "no draft to lock")
    if v.state == "locked":
        return {"version": v.version, "state": "locked", "locked_by": v.locked_by,
                "locked_at": v.locked_at.isoformat() if v.locked_at else None}
    left = _lock_blockers(v.content)
    if left["draft"] or left["flagged"]:
        raise HTTPException(
            409, f"{left['draft']} draft and {left['flagged']} flagged field(s) still need a "
                 f"decision before the form can be locked")
    v.state, v.locked_by, v.locked_at = "locked", cu.user.email, utcnow()
    s.commit()
    return {"version": v.version, "state": "locked", "locked_by": v.locked_by,
            "locked_at": v.locked_at.isoformat()}
