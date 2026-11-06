"""The edit check engine: one small evaluator per check type.

A check is data, a row with a type and a little JSON logic, not code. This
module only answers "does this check fail for this subject's answers?". It
never changes a value: a failed soft check becomes a query, a failed hard check
stops a save, and the data stays as entered.

A check whose inputs are not there yet passes, except `required`, whose whole
job is to notice that. A field answered Not done, Not applicable or Unknown
counts as answered and has no value to compare.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

TYPES = ("required", "range", "format", "cross_field", "cross_form", "temporal", "conditional", "manual")


@dataclass(frozen=True)
class Answer:
    value: object
    completion: str = "value"
    repeat: int = 1


@dataclass
class Context:
    """One subject's answers. field_id -> one Answer per repeat."""

    answers: dict[str, list[Answer]] = field(default_factory=dict)
    visit_of: dict[str, str] = field(default_factory=dict)
    visit_order: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Failure:
    code: str
    field_id: str
    repeat: int
    message: str
    severity: str


def _blank(a: Answer) -> bool:
    return a.completion == "value" and a.value in (None, "")


def _answered(ctx: Context, field_id: str) -> bool:
    return any(not _blank(a) for a in ctx.answers.get(field_id, []))


def _value(ctx: Context, field_id: str):
    """The first real value, or None when blank or marked not done."""
    for a in ctx.answers.get(field_id, []):
        if a.completion == "value" and a.value not in (None, ""):
            return a.value
    return None


def _number(v) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_OPS = {
    "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
}


def _compare(a, op: str, b) -> bool:
    x, y = _number(a), _number(b)
    if x is not None and y is not None:
        return _OPS[op](x, y)
    return _OPS[op](str(a).casefold(), str(b).casefold())


def _when(v, granularity: str):
    """A date for comparing, or a year when that is all the field holds."""
    text = str(v)
    try:
        if granularity == "year":
            return int(text[:4])
        return date.fromisoformat(text)
    except ValueError:
        return None


# ------------------------------------------------------------- evaluators
# Each returns (field_id, repeat) for the first failure, or None for a pass.

def _required(check, ctx):
    fid = check.field_ids[0]
    return None if _answered(ctx, fid) else (fid, 1)


def _range(check, ctx):
    lo, hi = check.logic.get("min"), check.logic.get("max")
    fid = check.field_ids[0]
    for a in ctx.answers.get(fid, []):
        x = _number(a.value) if a.completion == "value" else None
        if x is not None and ((lo is not None and x < lo) or (hi is not None and x > hi)):
            return fid, a.repeat
    return None


def _format_ok(logic: dict, v) -> bool:
    kind = logic.get("kind")
    text = str(v)
    if kind == "date":
        return _when(v, "day") is not None
    if kind == "integer":
        x = _number(v)
        return x is not None and x == int(x)
    if kind == "decimal":
        if _number(v) is None:
            return False
        places = logic.get("max_decimals")
        if places is None:
            return True
        try:
            return -Decimal(text).as_tuple().exponent <= places
        except InvalidOperation:
            return False
    if kind == "pattern":
        return re.fullmatch(logic.get("pattern", ""), text) is not None
    return True


def _format(check, ctx):
    fid = check.field_ids[0]
    for a in ctx.answers.get(fid, []):
        if a.completion == "value" and a.value not in (None, "") and not _format_ok(check.logic, a.value):
            return fid, a.repeat
    return None


def _cross_field(check, ctx):
    """Two fields, normally on one form: DBP below SBP."""
    a, b = _value(ctx, check.logic["a"]), _value(ctx, check.logic["b"])
    if a is None or b is None:
        return None
    return None if _compare(a, check.logic.get("op", "<"), b) else (check.logic["a"], 1)


def _cross_form(check, ctx):
    """A field at one visit against a field at another."""
    return _cross_field(check, ctx)


_TEMPORAL = {"before": "<", "on_or_before": "<=", "after": ">", "on_or_after": ">="}


def _temporal(check, ctx):
    gran = check.logic.get("granularity", "day")
    a, b = _value(ctx, check.logic["a"]), _value(ctx, check.logic["b"])
    if a is None or b is None:
        return None
    x, y = _when(a, gran), _when(b, gran)
    if x is None or y is None:
        return None
    return None if _OPS[_TEMPORAL[check.logic.get("op", "before")]](x, y) else (check.logic["a"], 1)


def _conditional(check, ctx):
    """If X equals V (or X is answered at all), then something must hold."""
    logic = check.logic
    x = logic["if_field"]
    if "equals" in logic:
        v = _value(ctx, x)
        if v is None or str(v).casefold() != str(logic["equals"]).casefold():
            return None
    elif not _answered(ctx, x):
        return None
    for fid in logic.get("then_required", []):
        if not _answered(ctx, fid):
            return fid, 1
    any_of = logic.get("then_any", [])
    if any_of and not any(_value(ctx, fid) not in (None, "No") for fid in any_of):
        return x, 1
    if logic.get("then_no_later_data"):
        visit = ctx.visit_of.get(x)
        later = ctx.visit_order[ctx.visit_order.index(visit) + 1:] if visit in ctx.visit_order else []
        if any(ctx.visit_of.get(fid) in later and _answered(ctx, fid) for fid in ctx.answers):
            return x, 1
    return None


EVALUATORS = {
    "required": _required, "range": _range, "format": _format, "cross_field": _cross_field,
    "cross_form": _cross_form, "temporal": _temporal, "conditional": _conditional,
}


def evaluate(check, ctx: Context) -> Failure | None:
    """A `manual` check is stored and listed, and never evaluated here."""
    fn = EVALUATORS.get(check.type)
    if fn is None:
        return None
    hit = fn(check, ctx)
    if hit is None:
        return None
    return Failure(code=check.code, field_id=hit[0], repeat=hit[1], message=check.message, severity=check.severity)
