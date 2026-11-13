"""Independently computed expected results.

This file imports nothing from the application package. Different code path on
purpose. It reads the tables with raw SQL, works out what a SAP row means from
the stored form JSON itself, and computes with the statistics module,
scipy.stats and collections. Only rows the sponsor has approved count, the same rule the app
applies.

Run directly:  python verification/expected_results.py [protocol_id]
Imported by:   ecrf/api/dashboard.py, which compares these against the app.
"""

import json
import math
import os
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from scipy import stats as scipy_stats


class _Postgres:
    """psycopg behind sqlite3's interface, so every query below is written once
    with ? placeholders. Opened directly, not through the app's engine."""

    def __init__(self, url: str):
        import psycopg

        self._con = psycopg.connect(url, prepare_threshold=None)

    def execute(self, sql, args=()):
        return self._con.execute(sql.replace("?", "%s"), args)

    def close(self):
        self._con.close()


def _connect(database_url: str):
    if database_url.startswith("sqlite"):
        return sqlite3.connect(database_url.replace("sqlite:///", ""))
    if database_url.startswith(("postgresql", "postgres:")):
        return _Postgres("postgresql://" + database_url.split("://", 1)[1])
    raise RuntimeError(f"verification script supports SQLite and Postgres, not {database_url.split(':', 1)[0]}")


def _json(value):
    """SQLite hands JSON columns back as text, Postgres as parsed values."""
    return json.loads(value) if isinstance(value, str) else value


def _placeholders(values) -> str:
    return ",".join("?" for _ in values)


def _approved(con, protocol_id, site_ids):
    sql = ("SELECT o.subject_id, o.visit, o.field_name, o.repeat_num, o.value_num, o.value_text "
           "FROM observation o ")
    args = [protocol_id]
    where = "WHERE o.protocol_id=? AND o.status='approved'"
    if site_ids is not None:
        sql += "JOIN subject su ON su.id = o.subject_ref "
        where += f" AND su.site_org_id IN ({_placeholders(site_ids)})"
        args += list(site_ids)
    return con.execute(sql + where, args).fetchall()


def _subject_count(con, protocol_id, site_ids) -> int:
    sql = "SELECT COUNT(*) FROM subject WHERE protocol_id=?"
    args = [protocol_id]
    if site_ids is not None:
        sql += f" AND site_org_id IN ({_placeholders(site_ids)})"
        args += list(site_ids)
    return con.execute(sql, args).fetchone()[0]


def _locked_form(con, protocol_id):
    row = con.execute("SELECT content FROM ecrf_version WHERE protocol_id=? AND state='locked' "
                      "ORDER BY version DESC LIMIT 1", (protocol_id,)).fetchone()
    return _json(row[0]) if row else None


def _subject_visit_means(rows, field):
    """subject -> visit -> mean of that visit's readings."""
    acc = defaultdict(lambda: defaultdict(list))
    for subject, visit, name, _repeat, num, _text in rows:
        if name == field and num is not None:
            acc[subject][visit].append(num)
    return {subj: {v: sum(xs) / len(xs) for v, xs in visits.items()} for subj, visits in acc.items()}


def _block(values):
    if not values:
        return None
    return {"n": len(values), "mean": statistics.mean(values),
            "sd": statistics.stdev(values) if len(values) > 1 else None,
            "median": statistics.median(values), "min": min(values), "max": max(values)}


def _descriptive(means, baseline, analysis):
    b = _block([v[baseline] for v in means.values() if baseline in v]) if baseline else None
    a = _block([v[analysis] for v in means.values() if analysis in v]) if analysis else None
    return {"baseline": b, "analysis": a} if (b or a) else None


def _paired(means, baseline, analysis):
    return [(v[baseline], v[analysis]) for v in means.values() if baseline in v and analysis in v]


def _change(means, baseline, analysis):
    pairs = _paired(means, baseline, analysis)
    n = len(pairs)
    if n < 2:
        return None
    diffs = [e - b for b, e in pairs]
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    if sd == 0:
        return {"n": n, "mean": mean, "sd": 0.0, "ci_low": mean, "ci_high": mean, "t": None, "p": None}
    se = sd / math.sqrt(n)
    margin = float(scipy_stats.t.ppf(0.975, n - 1)) * se
    t = mean / se
    return {"n": n, "mean": mean, "sd": sd, "ci_low": mean - margin, "ci_high": mean + margin,
            "t": t, "p": 2 * float(scipy_stats.t.sf(abs(t), n - 1))}


def _meets(x, op, threshold):
    if op == "<":
        return x < threshold
    if op == "<=":
        return x <= threshold
    if op == ">":
        return x > threshold
    if op == ">=":
        return x >= threshold
    raise ValueError(op)


def _responders(means, baseline, analysis, rule):
    pairs = _paired(means, baseline, analysis)
    if not pairs:
        return None
    k = 0
    for b, e in pairs:
        if _meets(e - b if rule["on"] == "change" else e, rule["op"], rule["value"]):
            k += 1
    ci = scipy_stats.binomtest(k, len(pairs)).proportion_ci(0.95, method="wilson")
    return {"responders": k, "n": len(pairs), "rate": k / len(pairs), "ci_low": ci.low, "ci_high": ci.high}


def _parse(text):
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        return None


def _teae(rows, field, date_field, baseline):
    first, at_baseline, events = {}, {}, defaultdict(list)
    for subject, visit, name, _repeat, _num, text in rows:
        day = _parse(text)
        if day is None:
            continue
        if name == date_field:
            first[subject] = min(first.get(subject, day), day)
            if visit == baseline:
                at_baseline[subject] = min(at_baseline.get(subject, day), day)
        if name == field:
            events[subject].append(day)
    if not first:
        return None
    started = {**first, **at_baseline}
    count = 0
    for subject, begin in started.items():
        if any(day >= begin for day in events.get(subject, [])):
            count += 1
    return {"subjects": count, "denominator": len(started), "percent": 100.0 * count / len(started)}


def _frequency(rows, field, visit, subjects):
    first = {}
    for subject, seen, name, repeat, _num, text in rows:
        if name == field and seen == visit and text is not None and (subject not in first or repeat < first[subject][0]):
            first[subject] = (repeat, text)
    if not first:
        return None
    tally = Counter(text for _, text in first.values())
    n = sum(tally.values())
    return {"n": n, "missing": max(subjects - n, 0),
            "categories": {k: {"count": c, "percent": c * 100.0 / n} for k, c in tally.items()}}


def _missing(rows, field, slots, subjects):
    expected = subjects * sum(slots.values())
    if not expected:
        return None
    present = set()
    for subject, visit, name, repeat, num, text in rows:
        if name == field and visit in slots and repeat <= slots[visit] and (num is not None or text is not None):
            present.add((subject, visit, repeat))
    return {"percent": 100.0 * (expected - len(present)) / expected, "expected": expected, "present": len(present)}


def item_results(database_url: str, protocol_id: int, item_id: int, site_ids=None) -> dict:
    """Every calculation that applies to one SAP row, or {} if it cannot run."""
    con = _connect(database_url)
    try:
        found = con.execute("SELECT kind, field_id, baseline_visit_id, analysis_visit_id, responder_rule "
                            "FROM sap_item WHERE id=? AND protocol_id=?", (item_id, protocol_id)).fetchone()
        form = _locked_form(con, protocol_id)
        if found is None or form is None:
            return {}
        kind, field_id, baseline, analysis, rule_json = found
        rule = _json(rule_json) if rule_json else None
        rows = _approved(con, protocol_id, site_ids)
        subjects = _subject_count(con, protocol_id, site_ids)
    finally:
        con.close()

    field, date_field, field_type = None, None, None
    per_visit = {}
    all_fields = [(f["visit"], x) for f in form["forms"] for x in f["fields"]]
    for _, x in all_fields:
        if x.get("field_id") == field_id:
            field, field_type = x["name"], x["type"]
        if x.get("cdash") == "SVSTDTC" and date_field is None:
            date_field = x["name"]
    if field is None:
        return {}
    for visit, x in all_fields:
        if x["name"] == field and x.get("collected", True):
            per_visit[visit] = x.get("repeats", 1)
    slots = per_visit if kind == "safety" else {v: n for v, n in per_visit.items() if v in (baseline, analysis)}

    means = _subject_visit_means(rows, field)
    out = {"percent_missing": _missing(rows, field, slots, subjects)}
    numeric = field_type in ("integer", "decimal")
    if kind in ("endpoint", "baseline", "disposition") and numeric:
        out["descriptive"] = _descriptive(means, baseline, analysis)
    if kind in ("baseline", "disposition") and field_type in ("choice", "boolean", "text"):
        out["frequency"] = _frequency(rows, field, baseline if kind == "baseline" else analysis, subjects)
    if kind == "endpoint":
        out["change_from_baseline"] = _change(means, baseline, analysis)
        if rule:
            out["responder_rate"] = _responders(means, baseline, analysis, rule)
    if kind == "safety":
        out["teae_count"] = _teae(rows, field, date_field, baseline)
    return out


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    url = os.getenv("DATABASE_URL") or f"sqlite:///{Path(__file__).resolve().parent.parent / 'ecrf.db'}"
    connection = _connect(url)
    items = connection.execute("SELECT id, label FROM sap_item WHERE protocol_id=?", (pid,)).fetchall()
    connection.close()
    for item, label in items:
        print(label, json.dumps(item_results(url, pid, item), indent=2))
