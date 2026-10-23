"""Synthetic observation data for the dashboard demo.

Twenty made-up subjects spread across the site organisations, a plausible
blood pressure drop, three dropouts so the mean-change calculation has
something to get wrong, and about 70% of rows already approved so the
sponsor's review page has work on it while the statistics still compute.
The numbers are deterministic (fixed seed) so the independent verification
script can be compared against them.
"""

import random

from sqlalchemy.orm import Session

from ecrf.storage.models import Observation, Organisation, Subject, utcnow

VISITS = ["Screening", "Day 1", "Week 4", "Week 12"]
DROPOUTS = {7, 13, 18}      # no Week 12
LATE_DROPOUT = {4}          # no Week 4 or Week 12
APPROVED_SHARE = 0.7


def seed(s: Session, protocol_id: int, sites: list[Organisation], version_id: int | None,
         n: int = 20, seed: int = 401) -> int:
    rng = random.Random(seed)
    counters = {o.id: 0 for o in sites}
    subjects: list[Subject] = []
    for i in range(1, n + 1):
        site = sites[(i - 1) % len(sites)]
        counters[site.id] += 1
        subj = Subject(protocol_id=protocol_id, site_org_id=site.id,
                       code=f"{site.code}-{counters[site.id]:03d}", created_by="seed")
        s.add(subj)
        subjects.append(subj)
    s.flush()

    rows: list[Observation] = []

    def add(subj: Subject, visit, field, rep=1, num=None, text=None):
        approved = rng.random() < APPROVED_SHARE
        rows.append(Observation(
            protocol_id=protocol_id, subject_id=subj.code, subject_ref=subj.id,
            ecrf_version_id=version_id, visit=visit, field_name=field, repeat_num=rep,
            value_num=num, value_text=text, synthetic=True, entered_by="seed",
            status="approved" if approved else "entered",
            approved_by="seed" if approved else None, approved_at=utcnow() if approved else None,
        ))

    for i, subj in enumerate(subjects, start=1):
        base_sys = rng.randint(142, 158)
        base_dia = rng.randint(88, 98)
        weight = round(rng.uniform(62, 96), 1)
        drop_total = rng.uniform(8, 22)       # total fall by week 12
        add(subj, "Screening", "Sex", text=rng.choice(["Male", "Female"]))
        add(subj, "Screening", "Height", num=round(rng.uniform(155, 188), 1))

        for visit in VISITS:
            if visit == "Week 12" and i in DROPOUTS | LATE_DROPOUT:
                continue
            if visit == "Week 4" and i in LATE_DROPOUT:
                continue
            frac = {"Screening": 0.0, "Day 1": 0.0, "Week 4": 0.55, "Week 12": 1.0}[visit]
            sys_mean = base_sys - drop_total * frac
            dia_mean = base_dia - (drop_total * 0.45) * frac
            for rep in (1, 2, 3):
                add(subj, visit, "Systolic Blood Pressure", rep, round(sys_mean + rng.uniform(-3, 3)))
                add(subj, visit, "Diastolic Blood Pressure", rep, round(dia_mean + rng.uniform(-2, 2)))
            add(subj, visit, "Position", text="Seated")
            if visit in ("Screening", "Day 1", "Week 12"):
                add(subj, visit, "Weight", num=round(weight + rng.uniform(-0.8, 0.8), 1))
            if visit in ("Screening", "Week 4", "Week 12"):
                add(subj, visit, "HbA1c", num=round(rng.uniform(5.2, 6.4), 1))
                add(subj, visit, "Fasting Plasma Glucose", num=round(rng.uniform(4.6, 6.8), 1))
    s.add_all(rows)
    s.flush()
    return len(rows)
