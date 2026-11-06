"""The approved calculations.

No field or visit is named here. Each function is told what to work on by an
Analysis, which comes from one row of the sponsor's statistical analysis plan.
Each docstring records the decision behind it, because "change from baseline"
is vaguer than it sounds and the next person should not have to re-guess.

Rules shared by all of them:
  - Only approved rows reach this file. registry.load_frame sees to that.
  - Repeats within a visit are averaged first, per subject, and the statistics
    run on those per-subject means.
  - Missing data is not imputed. A subject without a value is left out of the
    statistic and counted by percent_missing.
"""

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class Analysis:
    """One SAP row, resolved against the locked form."""

    kind: str
    field: str
    baseline: str | None
    analysis: str | None
    rule: dict | None
    # visit -> repeats, from the form definition, for the visits this item covers
    expected: dict[str, int]
    # registered subjects in the caller's scope
    subjects: int
    # the form's visit date field, found by its code rather than by name
    visit_date: str | None = None


def _visit_means(df: pd.DataFrame, field: str) -> pd.DataFrame:
    d = df[(df.field_name == field) & df.value_num.notna()]
    d = d.assign(value_num=d.value_num.astype(float))
    return d.groupby(["subject_id", "visit"], as_index=False).value_num.mean()


def _summary(values: pd.Series) -> dict | None:
    n = len(values)
    if n == 0:
        return None
    return {"n": n, "mean": float(values.mean()), "sd": float(values.std(ddof=1)) if n > 1 else None,
            "median": float(values.median()), "min": float(values.min()), "max": float(values.max())}


def descriptive(df: pd.DataFrame, a: Analysis) -> dict | None:
    """n, mean, sd, median, min and max at the baseline and analysis visits.
    sd needs two subjects, so with one it is blank rather than zero."""
    m = _visit_means(df, a.field)
    baseline = _summary(m[m.visit == a.baseline].value_num) if a.baseline else None
    analysis = _summary(m[m.visit == a.analysis].value_num) if a.analysis else None
    if baseline is None and analysis is None:
        return None
    return {"baseline": baseline, "analysis": analysis}


def _pairs(df: pd.DataFrame, a: Analysis) -> tuple[pd.Series, pd.Series]:
    """Per-subject baseline and analysis values, for subjects who have both."""
    m = _visit_means(df, a.field)
    base = m[m.visit == a.baseline].set_index("subject_id").value_num
    end = m[m.visit == a.analysis].set_index("subject_id").value_num
    both = base.index.intersection(end.index)
    return base[both], end[both]


def change_from_baseline(df: pd.DataFrame, a: Analysis) -> dict | None:
    """Analysis value minus baseline value, paired by subject, with a 95% CI
    from the t distribution and a paired t-test.

    Subjects without both values are EXCLUDED, not treated as zero change.
    Counting them is the dropout bug: with four completers at -18, -12, -20, -4
    the correct mean is -13.5, and dividing by five gives -10.8, which looks
    entirely plausible and is wrong.
    """
    base, end = _pairs(df, a)
    n = len(base)
    if n < 2:
        return None
    diffs = end - base
    mean, sd = float(diffs.mean()), float(diffs.std(ddof=1))
    if sd == 0:
        # Every subject moved by the same amount, so no t statistic exists.
        return {"n": n, "mean": mean, "sd": 0.0, "ci_low": mean, "ci_high": mean, "t": None, "p": None}
    test = stats.ttest_rel(end, base)
    ci = test.confidence_interval(0.95)
    return {"n": n, "mean": mean, "sd": sd, "ci_low": float(ci.low), "ci_high": float(ci.high),
            "t": float(test.statistic), "p": float(test.pvalue)}


_OPS = {"<": lambda x, y: x < y, "<=": lambda x, y: x <= y, ">": lambda x, y: x > y, ">=": lambda x, y: x >= y}


def responder_rate(df: pd.DataFrame, a: Analysis) -> dict | None:
    """Responders over subjects with both values, with a Wilson 95% CI. The
    rule tests either the change or the analysis value against a threshold."""
    base, end = _pairs(df, a)
    n = len(base)
    if n == 0:
        return None
    tested = end - base if a.rule["on"] == "change" else end
    k = int(sum(_OPS[a.rule["op"]](float(x), float(a.rule["value"])) for x in tested))
    p = k / n
    z = float(stats.norm.ppf(0.975))
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return {"responders": k, "n": n, "rate": p, "ci_low": centre - half, "ci_high": centre + half}


def _day(text) -> date | None:
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        return None


def _dates(df: pd.DataFrame, field: str | None) -> pd.DataFrame:
    d = df[df.field_name == field]
    return d.assign(day=d.value_text.map(_day)).dropna(subset=["day"])


def teae_count(df: pd.DataFrame, a: Analysis) -> dict | None:
    """Subjects with any adverse event starting on or after the start of
    treatment. The item's field is the AE start date.

    The start is the date of the item's baseline visit when one is set, which
    is how a plan points at the first dosing visit. Otherwise it is the
    subject's first visit date. The denominator is subjects with a start date:
    without one, nothing can be said about whether an event came after it.
    """
    visits = _dates(df, a.visit_date)
    if visits.empty:
        return None
    start = visits.groupby("subject_id").day.min().to_dict()
    if a.baseline:
        start.update(visits[visits.visit == a.baseline].groupby("subject_id").day.min().to_dict())
    events = _dates(df, a.field)
    emergent = {x.subject_id for x in events.itertuples() if x.subject_id in start and x.day >= start[x.subject_id]}
    return {"subjects": len(emergent), "denominator": len(start), "percent": 100.0 * len(emergent) / len(start)}


def percent_missing(df: pd.DataFrame, a: Analysis) -> dict | None:
    """Share of the slots the form says should exist that hold no approved value.

    Expected comes from the form definition times the registered subjects, never
    from the rows themselves: a dropout, or a subject with nothing entered, has
    no rows to count and is exactly what this must catch. A "not done" answer
    has no value, so it counts as missing here.
    """
    expected = a.subjects * sum(a.expected.values())
    if expected == 0:
        return None
    d = df[(df.field_name == a.field) & df.visit.isin(list(a.expected))
           & (df.value_num.notna() | df.value_text.notna())]
    d = d[d.repeat_num <= d.visit.map(a.expected)]
    present = d.drop_duplicates(["subject_id", "visit", "repeat_num"]).shape[0]
    return {"percent": 100.0 * (expected - present) / expected, "expected": expected, "present": present}
