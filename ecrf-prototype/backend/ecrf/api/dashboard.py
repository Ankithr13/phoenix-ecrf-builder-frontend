"""Dashboard numbers. Every scalar statistic is returned alongside the
independently computed value and a pass/fail marker. A number that only
checks itself proves nothing."""

import math
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ecrf.auth import scope
from ecrf.auth.permissions import CurrentUser, require
from ecrf.config import config
from ecrf.schema import DraftECRF
from ecrf.stats import registry
from ecrf.storage import db
from ecrf.storage.models import Observation

# The verification package deliberately lives outside ecrf/ and imports
# nothing from it. We import it here only to compare.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verification import expected_results as independent

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
TOLERANCE = 0.01


def _jsonable(v):
    """Replace NaN and infinity with None so the response can be serialised.

    A calculation legitimately returns NaN when it has nothing to work on.
    Mean change from baseline, for example, needs a subject to have both a
    Day 1 and a Week 12 reading; a protocol whose visits are named anything
    else yields no pairs at all. json.dumps then refuses the value and the
    whole dashboard returns 500, which reads as the app being broken rather
    than the statistic being unavailable.
    """
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and not math.isfinite(v))


def _status(a, b) -> str:
    """Pass needs a number on both sides that agree. Two blanks agreeing with
    each other prove nothing, so a statistic that could not be computed is
    not available, never a pass."""
    if _missing(a) or _missing(b):
        return "not_available"
    if isinstance(a, dict) and isinstance(b, dict):
        return "pass" if a == b else "fail"
    try:
        return "pass" if abs(float(a) - float(b)) < TOLERANCE else "fail"
    except (TypeError, ValueError):
        return "fail"


@router.get("/calculations")
def calculations(cu: CurrentUser = Depends(require("dashboard.view"))):
    return registry.available()


@router.get("/{protocol_id}")
def dashboard(protocol_id: int, cu: CurrentUser = Depends(require("dashboard.view")),
              s: Session = Depends(db.get_session)):
    p = scope.protocol_or_404(s, cu, protocol_id)

    # --- extraction summary from the latest version (real data) ---
    v = db.latest_version(s, protocol_id)
    extraction = None
    if v:
        draft = DraftECRF.model_validate(v.content)
        per_visit = [{"visit": f.visit, "fields": len(f.fields),
                      "flagged": sum(1 for x in f.fields if x.issue != "none"),
                      "approved": sum(1 for x in f.fields if x.status == "approved")}
                     for f in draft.forms]
        extraction = {"version": v.version, "summary": draft.summary,
                      "per_visit": per_visit, "rejections": len(draft.rejections),
                      "backend": draft.backend, "model": draft.model}

    # --- statistics over observation data ---
    df = registry.load_frame(s, protocol_id)
    stats = []
    # Statistics describe the whole study, and a person scoped to some sites
    # may not see those numbers. Stage 7 gives them per-site results.
    if not df.empty and cu.site_ids is None:
        for name, meta in registry.CALCULATIONS.items():
            app_val = registry.run(name, df)
            ind_fn = getattr(independent, {"mean_change_systolic": "mean_change_systolic",
                                           "subjects_per_visit": "subjects_per_visit",
                                           "percent_missing": "percent_missing"}[name])
            ind_val = ind_fn(config.database_url, protocol_id)
            status = _status(app_val, ind_val)
            stats.append({
                "name": name, "label": meta["label"], "unit": meta["unit"], "kind": meta["kind"],
                "app": _jsonable(app_val), "independent": _jsonable(ind_val),
                "status": status, "pass": status == "pass",
            })
        subjects = int(df.subject_id.nunique())
        readings = len(df)
    else:
        subjects, readings = 0, 0
    if cu.site_ids is not None:
        scoped = s.scalars(scope.visible_observations(cu, protocol_id)).all()
        subjects = len({o.subject_id for o in scoped if o.status == "approved"})
        readings = sum(1 for o in scoped if o.status == "approved")
        entered_total = len(scoped)
    else:
        entered_total = s.scalar(select(func.count(Observation.id)).where(
            Observation.protocol_id == protocol_id, Observation.status != "draft")) or 0

    return {"protocol": {"id": p.id, "name": p.name}, "extraction": extraction,
            "data": {"subjects": subjects, "readings": readings, "entered_total": entered_total},
            "stats": stats}


@router.post("/{protocol_id}/unsupported")
def unsupported(protocol_id: int, name: str, cu: CurrentUser = Depends(require("sap.edit")),
                s: Session = Depends(db.get_session)):
    """Exists only to demonstrate the refusal. Anything not in the registry
    is refused, never approximated. A registered name is not what this route
    is for, so it is a bad request rather than a pretend answer."""
    scope.protocol_or_404(s, cu, protocol_id)
    if name in registry.CALCULATIONS:
        raise HTTPException(400, f"'{name}' is an approved calculation; read it from the dashboard.")
    raise HTTPException(
        403, f"'{name}' is not an approved calculation. The approved set is: "
             f"{', '.join(registry.CALCULATIONS)}. Adding one means writing, testing "
             f"and independently verifying it first.")
