"""Running checks against what is in the database, and turning failed soft
checks into system queries. The evaluators themselves are in engine.py."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.checks import builtin
from ecrf.checks.engine import Answer, Context, Failure, evaluate
from ecrf.schema import DraftECRF
from ecrf.storage.models import (
    LIVE_QUERY,
    EditCheck,
    Observation,
    ObservationHistory,
    Protocol,
    Query,
    Subject,
    utcnow,
)

AUTO_ANSWER = "Value changed, check now passes"


def ensure(s: Session, p: Protocol, draft: DraftECRF, version: int) -> None:
    """Generate the built-in checks once. Called at lock, and on first use for
    a form locked before checks existed."""
    if s.scalars(select(EditCheck.id).where(EditCheck.protocol_id == p.id, EditCheck.origin == "builtin")).first():
        return
    for spec in builtin.specs(draft):
        s.add(EditCheck(protocol_id=p.id, code=spec.code, form=spec.form, field_ids=spec.field_ids, type=spec.type,
                        logic=spec.logic, message=spec.message, severity=spec.severity, owner="system",
                        origin="builtin", form_version=version))
    s.flush()


def context_from(draft: DraftECRF, answers: dict[tuple[str, str, int], tuple[object, str]]) -> Context:
    """`answers` maps (visit, field name, repeat) to (value, completion)."""
    ctx = Context(visit_order=[f.visit for f in draft.forms])
    ids: dict[tuple[str, str], str] = {}
    for form in draft.forms:
        for f in form.fields:
            ctx.visit_of[f.field_id] = form.visit
            ids[(form.visit, f.name)] = f.field_id
    for (visit, name, repeat), (value, completion) in sorted(answers.items(), key=lambda kv: kv[0][2]):
        fid = ids.get((visit, name))
        if fid:
            ctx.answers.setdefault(fid, []).append(Answer(value, completion, repeat))
    return ctx


def _subject_rows(s: Session, p: Protocol, subj: Subject) -> list[Observation]:
    return list(s.scalars(select(Observation).where(
        Observation.protocol_id == p.id, Observation.subject_id == subj.code)))


def _answers(rows: list[Observation]) -> dict[tuple[str, str, int], tuple[object, str]]:
    return {(o.visit, o.field_name, o.repeat_num):
            (o.value_num if o.value_num is not None else o.value_text, o.completion_status) for o in rows}


def _relevant(check: EditCheck, visit: str, ctx: Context) -> bool:
    return check.form is None or check.form == visit or any(ctx.visit_of.get(f) == visit for f in check.field_ids)


def failures(s: Session, p: Protocol, draft: DraftECRF, subj: Subject, visit: str,
             overlay: dict[tuple[str, int], tuple[object, str]] | None = None) -> list[tuple[EditCheck, Failure]]:
    """What fails for this subject at this visit. `overlay` holds values as
    they would stand if the form on screen were saved, for checking in advance."""
    answers = _answers(_subject_rows(s, p, subj))
    for (name, repeat), pair in (overlay or {}).items():
        answers[(visit, name, repeat)] = pair
    ctx = context_from(draft, answers)
    checks = s.scalars(select(EditCheck).where(
        EditCheck.protocol_id == p.id, EditCheck.enabled.is_(True)).order_by(EditCheck.id))
    out = []
    for check in checks:
        if _relevant(check, visit, ctx):
            hit = evaluate(check, ctx)
            if hit:
                out.append((check, hit))
    return out


def _settled(s: Session, subj: Subject, check: EditCheck, target: Observation | None) -> bool:
    """A person closed this check's query and its value has not changed since.
    Their decision stands: only a new value is a reason to ask again."""
    closed = s.scalars(select(Query).where(
        Query.subject_ref == subj.id, Query.check_key == str(check.id), Query.status == "closed")
        .order_by(Query.closed_at.desc())).first()
    if closed is None:
        return False
    if target is None:
        return True
    return s.scalars(select(ObservationHistory.id).where(
        ObservationHistory.observation_id == target.id,
        ObservationHistory.changed_at > closed.closed_at)).first() is None


def _target(draft: DraftECRF, rows: list[Observation], hit: Failure, visit: str) -> tuple[Observation | None, str]:
    where = {f.field_id: (form.visit, f.name) for form in draft.forms for f in form.fields}
    target_visit, name = where.get(hit.field_id, (visit, ""))
    for o in rows:
        if (o.visit, o.field_name, o.repeat_num) == (target_visit, name, hit.repeat):
            return o, target_visit
    return None, target_visit


def would_raise(s: Session, p: Protocol, draft: DraftECRF, subj: Subject, visit: str,
                overlay: dict[tuple[str, int], tuple[object, str]] | None = None) -> list[tuple[EditCheck, Failure]]:
    """The soft failures that would become new queries: not those with a live
    query already, nor those a person has settled."""
    live = set(s.scalars(select(Query.check_key).where(
        Query.protocol_id == p.id, Query.subject_ref == subj.id, Query.status.in_(LIVE_QUERY),
        Query.check_key.is_not(None))))
    rows = _subject_rows(s, p, subj)
    out = []
    for check, hit in failures(s, p, draft, subj, visit, overlay):
        if hit.severity == "soft" and str(check.id) not in live and not _settled(s, subj, check, _target(draft, rows, hit, visit)[0]):
            out.append((check, hit))
    return out


def sync_queries(s: Session, p: Protocol, draft: DraftECRF, subj: Subject, visit: str) -> list[Query]:
    """Bring the system queries in line with the checks at this visit. A failed
    soft check has one live query, never two. A query whose check now passes is
    answered and left for a person to close. Returns the queries raised."""
    fails = {check.id: hit for check, hit in failures(s, p, draft, subj, visit) if hit.severity == "soft"}
    ctx = context_from(draft, {})
    rows = _subject_rows(s, p, subj)
    live = {q.check_key: q for q in s.scalars(select(Query).where(
        Query.protocol_id == p.id, Query.subject_ref == subj.id, Query.raised_by == "system",
        Query.status.in_(LIVE_QUERY), Query.check_key.is_not(None)))}
    raised: list[Query] = []
    for check in s.scalars(select(EditCheck).where(EditCheck.protocol_id == p.id).order_by(EditCheck.id)):
        q = live.get(str(check.id))
        hit = fails.get(check.id)
        if hit is None:
            if q is not None and q.status == "open" and _relevant(check, visit, ctx):
                q.status, q.answer_text, q.answered_by, q.answered_at = "answered", AUTO_ANSWER, "system", utcnow()
            continue
        if q is not None:
            if q.status == "answered" and q.answered_by == "system":
                q.status, q.answer_text, q.answered_by, q.answered_at = "open", None, None, None
            continue
        o, target_visit = _target(draft, rows, hit, visit)
        if _settled(s, subj, check, o):
            continue
        query = Query(protocol_id=p.id, site_org_id=subj.site_org_id, subject_ref=subj.id,
                      visit=None if o is not None else target_visit, observation_id=o.id if o is not None else None,
                      raised_by="system", raised_by_org="sponsor", raised_by_role="system", text=hit.message,
                      status="open", check_code=check.code, check_key=str(check.id))
        s.add(query)
        raised.append(query)
    s.flush()
    return raised
