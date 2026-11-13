"""The demo's story: 16 synthetic patients on PHX-401-201, told through the API.

Every step is done the way a person would do it: signed in as the right demo
account, through the real endpoint. So edit checks, system queries, history
rows, the access log and notifications are all written by the app itself.
The story runs over the 28 days before `as_of`. The seed sets the app's clock
(ecrf/clock.py) before each step instead of editing timestamps afterwards.

Values come from a fixed random seed. The same `as_of` gives the same values
and the same timestamps on every run. Visit dates are counted back from
`as_of`, so a build on a later day moves the dates and nothing else.

Visits: Day 1 is the baseline and Week 12 the final visit, with Week 4 between
them on a straight line plus a little noise. Foundation and Screening are
filled for everyone. Nobody withdraws, so Early Termination stays empty.

Patients are BGH-001 to BGH-010 and MRC-001 to MRC-006, so the live
walkthrough's next Boston General patient is BGH-011.
"""

import random
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from ecrf import clock
from ecrf.storage import db
from ecrf.storage.models import Organisation, Query, Signoff, Subject

SEED = 401201
BASELINE, MIDDLE, FINAL = "Day 1", "Week 4", "Week 12"
FILLED = ("Foundation", "Screening", BASELINE, MIDDLE, FINAL)
SPAN = 28

BUILDER, DM, CRA = "builder@phoenix.demo", "dm@phoenix.demo", "cra@phoenix.demo"
PI = {"BGH": "pi@bgh.demo", "MRC": "pi@mrc.demo"}
CRC = {"BGH": "crc@bgh.demo", "MRC": "crc@mrc.demo"}
INBOXES = (DM, CRA, PI["BGH"], CRC["BGH"], CRC["MRC"])

BGH = [f"BGH-{n:03d}" for n in range(1, 11)]
MRC = [f"MRC-{n:03d}" for n in range(1, 7)]
CODES = BGH + MRC
AE_PATIENTS = ("BGH-002", "BGH-008", "MRC-003")

# Screening's Date of Birth is a full date of birth, which the demo never
# holds. The form keeps Foundation's Year of birth; this field is rejected
# before the lock, the way a builder would.
REJECTED = [("Screening", "Date of Birth",
             "Only year of birth is collected (Foundation). No full dates of birth in this study.")]

RACES = ["WHITE", "BLACK OR AFRICAN AMERICAN", "ASIAN", "WHITE", "MULTIPLE", "AMERICAN INDIAN OR ALASKA NATIVE",
         "WHITE", "OTHER", "BLACK OR AFRICAN AMERICAN", "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER", "ASIAN",
         "NOT REPORTED", "WHITE", "BLACK OR AFRICAN AMERICAN", "UNKNOWN", "ASIAN"]
ETHNICITIES = ["NOT HISPANIC OR LATINO", "HISPANIC OR LATINO", "NOT HISPANIC OR LATINO", "NOT REPORTED"]


# ------------------------------------------------------------------ values

@dataclass
class Patient:
    code: str
    site: str
    index: int
    readings: dict[str, dict[str, object]] = field(default_factory=dict)
    birth_year: int = 0
    sex: str = ""
    day1: date | None = None


def plan(as_of: date) -> list[Patient]:
    """Every value the seed will type, worked out before anything is sent.
    Pure: the same as_of always gives the same list."""
    rng = random.Random(SEED)
    out = []
    for i, code in enumerate(CODES):
        p = Patient(code=code, site=code[:3], index=i)
        p.birth_year = rng.randint(1950, 1990)
        p.sex = "F" if i % 2 else "M"
        height = round(rng.uniform(155, 190), 1)
        weight = round(rng.uniform(55, 100), 1)
        sbp0, dbp0, drop = rng.randint(140, 165), rng.randint(80, 100), rng.randint(3, 18)
        dbp_drop = rng.randint(0, 6)
        p.day1 = as_of - timedelta(days=112 + i % 8)
        screening, consent = p.day1 - timedelta(days=7), p.day1 - timedelta(days=10)

        # Screening sits near baseline. Week 4 is 28 of the 84 days along the
        # straight line from baseline to final, plus a little noise.
        noise_s, noise_m = rng.randint(-3, 3), rng.randint(-2, 2)
        sbp_s, dbp_s = sbp0 + noise_s, dbp0 + noise_s // 2
        sbp_m, dbp_m = round(sbp0 - drop * 28 / 84) + noise_m, round(dbp0 - dbp_drop * 28 / 84) + noise_m // 2
        sbp_f, dbp_f = sbp0 - drop, dbp0 - dbp_drop
        labs = [(rng.randint(380, 440), float(rng.randint(82, 98)), round(rng.uniform(4.8, 5.6), 1)) for _ in range(3)]
        weights = [round(weight + rng.uniform(-0.8, 0.8), 1) for _ in range(2)]
        ecg = "Abnormal not clinically significant" if i % 7 == 3 else "Normal"
        position = "Supine" if i % 5 == 4 else "Seated"

        p.readings = {
            "Foundation": {"Informed consent obtained": "Yes", "Consent date": consent.isoformat(),
                           "Consent version": "v2.0", "Year of birth": p.birth_year, "Sex": p.sex,
                           "Race": RACES[i], "Ethnicity": ETHNICITIES[i % len(ETHNICITIES)],
                           "Height": height, "Weight": weight, "Eligible": "Yes"},
            "Screening": {"Visit date": screening.isoformat(), "Sex": "Female" if p.sex == "F" else "Male",
                          "Systolic Blood Pressure": sbp_s, "Diastolic Blood Pressure": dbp_s,
                          "Position": position, "Weight": weight, "Height": height, "ECG Performed": "Yes",
                          "ECG Result": ecg, "QTcF Interval": labs[0][0], "Fasting Plasma Glucose": labs[0][1],
                          "HbA1c": labs[0][2]},
            BASELINE: {"Visit date": p.day1.isoformat(), "Systolic Blood Pressure": sbp0,
                       "Diastolic Blood Pressure": dbp0, "Position": position, "Weight": weights[0]},
            MIDDLE: {"Visit date": (p.day1 + timedelta(days=28)).isoformat(), "Systolic Blood Pressure": sbp_m,
                     "Diastolic Blood Pressure": dbp_m, "Position": position,
                     "Fasting Plasma Glucose": labs[1][1], "HbA1c": labs[1][2]},
            FINAL: {"Visit date": (p.day1 + timedelta(days=84)).isoformat(), "Systolic Blood Pressure": sbp_f,
                    "Diastolic Blood Pressure": dbp_f, "Position": position, "Weight": weights[1],
                    "ECG Performed": "Yes", "ECG Result": "Normal", "QTcF Interval": labs[2][0],
                    "Fasting Plasma Glucose": labs[2][1], "HbA1c": labs[2][2]},
        }
        # Blood pressure is taken three times at each visit. The statistics use
        # the first reading, so the line above is reading 1; the other two sit
        # close beside it.
        for visit in ("Screening", BASELINE, MIDDLE, FINAL):
            r = p.readings[visit]
            for name in ("Systolic Blood Pressure", "Diastolic Blood Pressure"):
                first = r[name]
                r[name] = [first, first + rng.randint(-3, 2), first + rng.randint(-3, 2)]
        if code in AE_PATIENTS:
            p.readings[MIDDLE].update({"Adverse Event Term": ["Headache", "Dizziness", "Nausea"][AE_PATIENTS.index(code)],
                                       "AE Start Date": (p.day1 + timedelta(days=10 + i)).isoformat(),
                                       "AE Severity": "Mild"})
        # The stories that need a particular value.
        if code == "BGH-006":
            p.readings[FINAL]["Systolic Blood Pressure"][0] = 260     # above EC-006's 250
        if code == "BGH-007":
            p.readings[BASELINE]["Diastolic Blood Pressure"][0] = 58  # the value the data manager queries
        if code == "MRC-005":
            p.readings[FINAL]["Systolic Blood Pressure"][0] = 140     # EC-007: diastolic not below systolic
            p.readings[FINAL]["Diastolic Blood Pressure"][0] = 150
        out.append(p)
    return out


# ------------------------------------------------------------------ the app

class SeedError(SystemExit):
    pass


def _ok(r, what: str):
    if r.status_code != 200:
        raise SeedError(f"demo seed: {what} failed: {r.status_code} {r.text[:400]}")
    return r.json()


class App:
    """Signed-in clients, one per account per moment, and the calls the story uses."""

    def __init__(self, new_client: Callable, password: str, pid: int):
        self.new_client, self.password, self.pid = new_client, password, pid
        self._clients: dict[tuple[str, date], object] = {}

    def as_(self, email: str):
        """A session lasts hours, not days, so each account signs in afresh on
        each day of the story, as a person would."""
        key = (email, clock.today())
        if key not in self._clients:
            c = self.new_client()
            _ok(c.post("/api/auth/login", json={"email": email, "password": self.password}), f"login {email}")
            self._clients[key] = c
        return self._clients[key]

    def rows(self, email: str, code: str, visit: str | None = None) -> list[dict]:
        url = f"/api/protocols/{self.pid}/data" + (f"?visit={visit}" if visit else "")
        return [r for r in _ok(self.as_(email).get(url), "read data") if r["subject"] == code]

    def row(self, email: str, code: str, visit: str, name: str, repeat: int = 1) -> dict:
        found = [r for r in self.rows(email, code, visit) if r["field"] == name and r["repeat"] == repeat]
        if len(found) != 1:
            raise SeedError(f"demo seed: expected one {name} for {code} at {visit}, found {len(found)}")
        return found[0]

    def register(self, site: str, code: str, birth_year: int, sex: str, enrolled: date) -> None:
        body = {"birth_year": birth_year, "sex": "Female" if sex == "F" else "Male", "enrolled_on": enrolled.isoformat()}
        made = _ok(self.as_(CRC[site]).post(f"/api/studies/{self.pid}/subjects", json=body), f"register {code}")
        if made["code"] != code:
            raise SeedError(f"demo seed: the server gave {made['code']} where the story expects {code}")

    def enter(self, site: str, code: str, visit: str, values: dict, reason: str | None = None, completion=None):
        readings = [{"field_name": k, "repeat_num": n, "value": x} for k, v in values.items()
                    for n, x in enumerate(v if isinstance(v, list) else [v], start=1)]
        readings += completion or []
        _ok(self.as_(CRC[site]).post("/api/data/enter", json={
            "protocol_id": self.pid, "subject_id": code, "visit": visit, "readings": readings, "reason": reason}),
            f"enter {code} {visit}")

    def submit(self, site: str, code: str, visit: str) -> dict:
        return _ok(self.as_(CRC[site]).post("/api/data/submit", json={
            "protocol_id": self.pid, "subject_id": code, "visit": visit}), f"submit {code} {visit}")

    def approve(self, code: str, visit: str, leave: tuple[str, ...] = ()) -> None:
        ids = [r["id"] for r in self.rows(DM, code, visit) if r["status"] != "approved" and r["field"] not in leave]
        _ok(self.as_(DM).post(f"/api/protocols/{self.pid}/data/approve", json={"observation_ids": ids}),
            f"approve {code} {visit}")

    def sign(self, code: str, visit: str) -> None:
        _ok(self.as_(PI[code[:3]]).post(f"/api/protocols/{self.pid}/signoff",
                              json={"subject_id": code, "visit": visit, "password": self.password}),
            f"sign {code} {visit}")

    def value_query(self, email: str, code: str, visit: str, name: str, text: str) -> int:
        oid = self.row(DM, code, visit, name)["id"]
        return _ok(self.as_(email).post(f"/api/data/{oid}/queries", json={"text": text}), f"query {code} {name}")["id"]

    def query(self, email: str, text: str, **about) -> int:
        return _ok(self.as_(email).post("/api/queries", json={"protocol_id": self.pid, "text": text, **about}),
                   f"query {about}")["id"]

    def answer(self, email: str, qid: int, text: str, new_value=None) -> None:
        body = {"text": text} | ({"new_value": new_value} if new_value is not None else {})
        _ok(self.as_(email).post(f"/api/queries/{qid}/answer", json=body), f"answer query {qid}")

    def close(self, qid: int, reason: str | None = None) -> None:
        _ok(self.as_(DM).post(f"/api/queries/{qid}/close", json={"reason": reason}), f"close query {qid}")

    def cancel(self, qid: int, reason: str) -> None:
        _ok(self.as_(DM).post(f"/api/queries/{qid}/cancel", json={"reason": reason}), f"cancel query {qid}")


# ------------------------------------------------------------------ the story

class Timeline:
    """Steps on a calendar, run in date and time order. Steps at the same
    moment run in the order they were added."""

    def __init__(self, as_of: date):
        self.as_of, self.steps = as_of, []

    def on(self, days_ago: int, hour: int, minute: int, fn: Callable) -> None:
        if not 1 <= days_ago <= SPAN + 1:
            raise ValueError(f"step {days_ago} days ago is outside the story")
        at = datetime.combine(self.as_of - timedelta(days=days_ago), time(hour, minute))
        self.steps.append((at, len(self.steps), fn))

    def run(self) -> None:
        for at, _, fn in sorted(self.steps, key=lambda s: (s[0], s[1])):
            clock.set_to(at)
            fn()


def _patient(t: Timeline, app: App, p: Patient, q: dict) -> None:
    """One patient's visits, from registration to sign-off. Enrolment is
    staggered over the first week, two Boston General patients a day and one
    Mercy patient a day, in code order, so the server hands out the codes the
    story expects. Then Week 4 five days later, Week 12 ten days later, each
    approved the next day, and the investigator signs two days after that."""
    code, site = p.code, p.site
    n = p.index if site == "BGH" else p.index - len(BGH)
    d0 = SPAN - n // 2 if site == "BGH" else SPAN - n
    m = p.index  # the minute: same-day steps run in code order

    def enter(visit: str) -> None:
        app.enter(site, code, visit, p.readings[visit])

    def enter_and_submit(visit: str) -> None:
        enter(visit)
        app.submit(site, code, visit)

    def keep(key: str, qid: int) -> None:
        q[key] = qid

    t.on(d0, 9, m, lambda: app.register(site, code, p.birth_year, p.sex, p.day1))
    for k, visit in enumerate(("Foundation", "Screening", BASELINE)):
        t.on(d0, 10 + k, m, lambda v=visit: enter_and_submit(v))
    for visit in ("Foundation", "Screening", BASELINE):
        # BGH-007's baseline diastolic waits: the data manager is about to query it.
        leave = ("Diastolic Blood Pressure",) if code == "BGH-007" and visit == BASELINE else ()
        t.on(d0 - 1, 14, m, lambda v=visit, lv=leave: app.approve(code, v, lv))

    if code == "BGH-010":
        # Week 4 did not happen. Week 12 is typed but not submitted yet.
        t.on(d0 - 5, 10, m, lambda: app.enter(site, code, MIDDLE, {}, completion=[
            {"field_name": "Visit date", "completion_status": "not_done", "completion_reason": "Patient travelling"}]))
        t.on(d0 - 5, 10, m, lambda: app.submit(site, code, MIDDLE))
        t.on(d0 - 6, 14, m, lambda: app.approve(code, MIDDLE))
        t.on(d0 - 10, 10, m, lambda: enter(FINAL))
        t.on(3, 11, 0, lambda: keep("BGH-010 patient", app.query(
            DM, "Please confirm whether the missed visit will be rescheduled.", subject_code=code)))
        return

    t.on(d0 - 5, 10, m, lambda: enter_and_submit(MIDDLE))
    t.on(d0 - 6, 14, m, lambda: app.approve(code, MIDDLE))

    if code in ("BGH-006", "MRC-005"):
        # The early visits are signed first, then the final visit raises a system query.
        for visit in ("Foundation", "Screening", BASELINE, MIDDLE):
            t.on(d0 - 7, 11, m, lambda v=visit: app.sign(code, v))
        t.on(d0 - 10, 10, m, lambda: enter_and_submit(FINAL))
        if code == "BGH-006":
            t.on(4, 10, 0, lambda: keep("BGH-006 visit", app.query(
                DM, "Please confirm the BP cuff size used.", subject_code=code, visit=FINAL)))
        return

    t.on(d0 - 10, 10, m, lambda: enter_and_submit(FINAL))
    if code == "BGH-008":
        t.on(d0 - 10, 15, m, lambda: keep("BGH-008", app.value_query(
            DM, code, FINAL, "Weight", "Please confirm the Week 12 weight against the source record.")))
        t.on(d0 - 11, 10, m, lambda: app.answer(CRC["BGH"], q["BGH-008"], "Value confirmed in source record"))
        t.on(d0 - 11, 15, m, lambda: app.close(q["BGH-008"], "Confirmed with the site"))
        t.on(d0 - 11, 15, m, lambda: app.approve(code, FINAL))
    else:
        t.on(d0 - 11, 14, m, lambda: app.approve(code, FINAL))
    if code == "BGH-009":
        t.on(d0 - 11, 15, m, lambda: keep("BGH-009", app.query(
            DM, "Please confirm the consent version signed at screening.", subject_code=code)))
        t.on(d0 - 11, 16, m, lambda: app.cancel(q["BGH-009"], "Raised on the wrong patient"))

    unsigned = {"BGH-004": FINAL, "BGH-007": BASELINE}.get(code)
    for visit in FILLED:
        if visit != unsigned:
            t.on(d0 - 12, 11, m, lambda v=visit: app.sign(code, v))


def _story(t: Timeline, app: App, patients: list[Patient], q: dict) -> None:
    """Who does what, and when. q collects the ids of the queries the story raises."""
    for p in patients:
        _patient(t, app, p, q)

    def keep(key: str, qid: int) -> None:
        q[key] = qid

    # After every patient has been signed, the queries that are left on screen.
    final_weight = next(p for p in patients if p.code == "BGH-005").readings[FINAL]["Weight"]
    t.on(9, 10, 0, lambda: keep("BGH-005", app.value_query(
        CRA, "BGH-005", FINAL, "Weight", "Weight does not match the source document. Please check.")))
    t.on(7, 11, 0, lambda: app.answer(CRC["BGH"], q["BGH-005"],
                                      "Scale reading copied wrongly; corrected from the source document",
                                      round(final_weight - 2.4, 1)))
    t.on(6, 14, 0, lambda: app.close(q["BGH-005"]))
    t.on(6, 14, 0, lambda: app.approve("BGH-005", FINAL))

    t.on(8, 10, 30, lambda: keep("BGH-007", app.value_query(
        DM, "BGH-007", BASELINE, "Diastolic Blood Pressure",
        "Diastolic 58 is low for this patient, please confirm against source.")))
    t.on(6, 9, 30, lambda: app.answer(CRC["BGH"], q["BGH-007"], "Transcription error", 85))

    t.on(5, 9, 0, lambda: keep("MRC-006", app.query(
        CRC["MRC"], "Is the Week 12 visit window plus or minus 3 days?")))
    t.on(2, 15, 0, lambda: app.answer(DM, q["MRC-006"], "Plus or minus 7 days, see protocol section 6."))


def _results(app: App, forms: list[dict]) -> None:
    """The analysis plan, added the way the Results tab adds it."""
    ids = {(form["visit"], f["name"]): f["field_id"] for form in forms for f in form["fields"]}
    rows = [
        {"field_id": ids[(BASELINE, "Weight")], "calculation": "descriptive", "baseline_visit_id": BASELINE},
        {"field_id": ids[("Foundation", "Sex")], "calculation": "frequency", "baseline_visit_id": "Foundation"},
        {"field_id": ids[(BASELINE, "Systolic Blood Pressure")], "calculation": "change_from_baseline",
         "baseline_visit_id": BASELINE, "analysis_visit_id": FINAL},
        {"field_id": ids[(BASELINE, "Systolic Blood Pressure")], "calculation": "responder_rate",
         "baseline_visit_id": BASELINE, "analysis_visit_id": FINAL,
         "responder_rule": {"on": "change", "op": "<=", "value": -10}},
        {"field_id": ids[(MIDDLE, "AE Start Date")], "calculation": "teae_count", "baseline_visit_id": BASELINE},
    ]
    for body in rows:
        _ok(app.as_(DM).post(f"/api/protocols/{app.pid}/sap", json=body), f"add result {body['calculation']}")


def _mark_read(app: App) -> None:
    """The three oldest for the data manager and the two oldest for the BGH
    coordinator, so their inboxes show both read and unread."""
    for email, n in ((DM, 3), (CRC["BGH"], 2)):
        c = app.as_(email)
        rows = sorted(_ok(c.get("/api/notifications"), "inbox"), key=lambda x: (x["created_at"], x["id"]))
        for row in rows[:n]:
            _ok(c.post(f"/api/notifications/{row['id']}/read"), "mark read")


def setup(new_client: Callable, password: str) -> tuple[int, list[dict]]:
    """Load the sample, approve its fields except the full date of birth,
    lock, and assign both sites. Returns the protocol id and the locked forms."""
    def signed_in(email: str):
        c = new_client()
        _ok(c.post("/api/auth/login", json={"email": email, "password": password}), f"login {email}")
        return c

    with db.session() as s:
        sites = [o.id for o in s.scalars(select(Organisation).where(Organisation.code.in_(("BGH", "MRC")))
                                         .order_by(Organisation.code))]
    builder = signed_in(BUILDER)
    pid = _ok(builder.post("/api/protocols/sample"), "load sample")["id"]
    visits = _ok(builder.post(f"/api/protocols/{pid}/extract/visits"), "find visits")["visits"]
    _ok(builder.put(f"/api/protocols/{pid}/visits", json={"visits": visits}), "confirm visits")
    _ok(builder.post(f"/api/protocols/{pid}/extract/fields"), "extract fields")
    forms = _ok(builder.get(f"/api/protocols/{pid}/draft"), "read draft")["draft"]["forms"]
    rejected = {(v, n) for v, n, _ in REJECTED}
    changes = [{"visit": form["visit"], "name": f["name"], "status": "approved"}
               for form in forms for f in form["fields"]
               if f["status"] != "approved" and (form["visit"], f["name"]) not in rejected]
    changes += [{"visit": v, "name": n, "status": "rejected", "reviewer_note": why} for v, n, why in REJECTED]
    _ok(builder.post(f"/api/protocols/{pid}/review", json={"changes": changes}), "decide fields")

    dm = signed_in(DM)
    _ok(dm.post(f"/api/protocols/{pid}/lock"), "lock form")
    for org_id in sites:
        _ok(dm.post(f"/api/protocols/{pid}/sites", json={"site_org_id": org_id}), "assign site")
    locked = _ok(dm.get(f"/api/protocols/{pid}/draft"), "read locked form")["draft"]["forms"]
    return pid, [{"visit": f["visit"], "fields": [x for x in f["fields"] if x["status"] == "approved"]} for f in locked]


def seed(new_client: Callable, password: str, as_of: date | None = None) -> dict:
    """Build the whole story. Expects the demo accounts to exist and nothing
    else. Returns the protocol id and the ids of the story's queries."""
    as_of = as_of or clock.today()
    try:
        clock.set_to(datetime.combine(as_of - timedelta(days=SPAN + 1), time(8, 0)))
        pid, forms = setup(new_client, password)
        app = App(new_client, password, pid)
        patients, queries = plan(as_of), {}
        t = Timeline(as_of)
        _story(t, app, patients, queries)
        t.on(1, 16, 0, lambda: _results(app, forms))
        t.on(1, 17, 0, lambda: _mark_read(app))
        t.run()
    finally:
        clock.set_to(None)
    return {"protocol_id": pid, "queries": queries, "as_of": as_of.isoformat()}


# ------------------------------------------------------------------ checks

def check(new_client: Callable, password: str, pid: int) -> dict:
    """Every state the demo needs is on screen. Raises on the first that is not.
    Returns the numbers the report quotes."""
    app = App(new_client, password, pid)
    problems: list[str] = []

    def need(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    with db.session() as s:
        codes = sorted(s.scalars(select(Subject.code).where(Subject.protocol_id == pid)))
        signed = s.scalars(select(Signoff).where(Signoff.protocol_id == pid, Signoff.invalidated_at.is_(None))).all()
        system = sorted((s.get(Subject, x.subject_ref).code, x.check_code, x.status) for x in s.scalars(
            select(Query).where(Query.protocol_id == pid, Query.raised_by == "system")))
    need(codes == sorted(CODES), f"patients are {codes}")
    need("BGH-011" not in codes, "BGH-011 is taken")

    statuses = {r["status"] for r in _ok(app.as_(CRC["BGH"]).get(f"/api/protocols/{pid}/data"), "site data")} | \
               {r["status"] for r in _ok(app.as_(DM).get(f"/api/protocols/{pid}/data"), "data")}
    for st in ("draft", "submitted", "approved"):
        need(st in statuses, f"no value is {st}")
    subjects = _ok(app.as_(DM).get(f"/api/studies/{pid}/subjects"), "patients")
    need(bool(signed), "no visit is signed")
    need(any(r["needs_signoff"] for r in subjects), "no visit needs sign-off")
    need(any(r["needs_resign"] for r in subjects), "no visit needs re-signing")

    queries = _ok(app.as_(DM).get("/api/queries"), "queries")
    by_status = {st: sum(1 for x in queries if x["status"] == st) for st in ("open", "answered", "closed", "cancelled")}
    for st, n in by_status.items():
        need(n > 0, f"no query is {st}")
    need(any(x["raised_by"] == "system" for x in queries), "no system query")
    need(any(x["raised_by_org"] == "site" for x in queries), "no query raised by a site")
    for about in ("study", "patient", "visit", "value"):
        need(any(x["about"] == about for x in queries), f"no {about}-level query")
    need(system == [("BGH-006", "EC-006", "open"), ("MRC-005", "EC-007", "open")],
         f"system queries are {system}, expected only EC-006 on BGH-006 and EC-007 on MRC-005")

    unread = {}
    for email in INBOXES:
        unread[email] = _ok(app.as_(email).get("/api/notifications/unread-count"), "unread")["unread"]
        need(unread[email] > 0, f"{email} has no unread notification")
    read = {email: sum(1 for x in _ok(app.as_(email).get("/api/notifications"), "inbox") if x["read_at"])
            for email in INBOXES}
    need(read[DM] == 3 and read[CRC["BGH"]] == 2, f"read notifications are {read}")

    stats = _ok(app.as_(DM).get(f"/api/dashboard/{pid}"), "dashboard")["stats"]
    need(len({x["item_id"] for x in stats}) == 5, "the plan does not have five results")
    for x in stats:
        need(x["status"] == "pass", f"{x['item_label']} {x['name']} is {x['status']}")

    if problems:
        raise SeedError("demo seed check failed:\n  " + "\n  ".join(problems))
    return {"unread": unread, "read": read, "queries": by_status, "stats": stats,
            "subjects": {r["code"]: r for r in subjects}}


def walkthrough(new_client: Callable, password: str, pid: int) -> list[str]:
    """The live walkthrough from the app guide, step by step. Run it on a copy
    of the seeded database; it changes what it touches."""
    app, done = App(new_client, password, pid), []
    crc = app.as_(CRC["BGH"])
    made = _ok(crc.post(f"/api/studies/{pid}/subjects"), "register")
    if made["code"] != "BGH-011":
        raise SeedError(f"walkthrough: registered {made['code']}, expected BGH-011")
    done.append("registered BGH-011")
    values = {"Informed consent obtained": "Yes", "Consent date": (clock.today() - timedelta(days=1)).isoformat(),
              "Consent version": "v1", "Year of birth": 1970, "Sex": "F", "Race": "WHITE",
              "Ethnicity": "NOT HISPANIC OR LATINO", "Eligible": "Yes", "Height": 150, "Weight": 190}
    app.enter("BGH", "BGH-011", "Foundation", values)
    bmi = app.row(CRC["BGH"], "BGH-011", "Foundation", "BMI")["value"]
    if bmi != "84.4":
        raise SeedError(f"walkthrough: BMI is {bmi}, expected 84.4")
    done.append("BMI 84.4")
    raised = app.submit("BGH", "BGH-011", "Foundation")["queries"]
    if [x["code"] for x in raised] != ["EC-006"]:
        raise SeedError(f"walkthrough: submit raised {raised}, expected one EC-006")
    done.append("submitted, EC-006 raised")
    app.close(raised[0]["id"], "Confirmed with the site")
    done.append("query closed")
    app.approve("BGH-011", "Foundation")
    done.append("approved")
    kinds = {(x["kind"], x["subject"]) for x in _ok(app.as_(PI["BGH"]).get("/api/notifications"), "pi inbox")}
    if ("signoff_needed", "BGH-011") not in kinds:
        raise SeedError("walkthrough: the investigator has no sign-off notification for BGH-011")
    app.sign("BGH-011", "Foundation")
    done.append("signed")
    if app.as_(DM).get(f"/api/protocols/{pid}/pdf/blank").status_code != 200:
        raise SeedError("walkthrough: blank eCRF PDF failed")
    done.append("blank eCRF PDF")
    return done


def copy_database(src: str, dst: str) -> None:
    """A consistent copy of a SQLite file, even while it is open."""
    a, b = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        a.backup(b)
    finally:
        a.close()
        b.close()
