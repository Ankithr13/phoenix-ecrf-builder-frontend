"""Sprint 3, stage 7: SAP mapping, biostatistics, dashboard tabs, listing, PDFs."""

import io
from datetime import timedelta
from pathlib import Path

import pdfplumber
import pytest
from conftest import AUDITOR, BGH, BUILDER, MONITOR, MRC, PASSWORD, PI
from sqlalchemy import select
from test_lock_sites_data import _org_id, entry, lock_and_assign, site_client, sponsor_draft, submit

from ecrf.schema import DraftECRF
from ecrf.stats import registry
from ecrf.storage import db
from ecrf.storage.models import (
    ECRFVersion,
    MonitorSite,
    Observation,
    Query,
    SapItem,
    Subject,
    User,
    UserAccessEvent,
    utcnow,
)

ROOT = Path(__file__).resolve().parent.parent
SBP = "Systolic Blood Pressure"


def _field_id(dm, pid, visit, name):
    forms = dm.get(f"/api/protocols/{pid}/draft").json()["draft"]["forms"]
    return next(f["field_id"] for form in forms if form["visit"] == visit for f in form["fields"] if f["name"] == name)


def _endpoint(dm, pid, field=SBP, rule=None):
    body = {"label": "Change in SBP", "kind": "endpoint", "field_id": _field_id(dm, pid, "Day 1", field),
            "baseline_visit_id": "Day 1", "analysis_visit_id": "Week 12", "unit": "mmHg", "responder_rule": rule,
            "method": "Paired t-test"}
    r = dm.post(f"/api/protocols/{pid}/sap", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _subjects(pid, site, codes):
    with db.session() as s:
        for code in codes:
            s.add(Subject(protocol_id=pid, site_org_id=_org_id(site), code=code, created_by="test"))


def _values(pid, rows, status="approved"):
    """rows: (subject code, visit, field, repeat, number or text)."""
    with db.session() as s:
        subj = {x.code: x.id for x in s.scalars(select(Subject).where(Subject.protocol_id == pid))}
        for code, visit, field, repeat, value in rows:
            num = value if isinstance(value, int | float) else None
            s.add(Observation(protocol_id=pid, subject_id=code, subject_ref=subj[code], visit=visit, field_name=field,
                              repeat_num=repeat, value_num=num, value_text=None if num is not None else value,
                              entered_by="test", status=status))


def _changes(pid, site="BGH"):
    """Four completers moving -18, -12, -20, -4, and one dropout."""
    codes = [f"{site}-{n:03d}" for n in range(1, 6)]
    _subjects(pid, site, codes)
    rows = []
    for code, base, end in zip(codes, (150, 140, 160, 130, 155), (132, 128, 140, 126, None), strict=True):
        rows.append((code, "Day 1", SBP, 1, base))
        if end is not None:
            rows.append((code, "Week 12", SBP, 1, end))
    _values(pid, rows)


def _stats(c, pid, name=None):
    rows = c.get(f"/api/dashboard/{pid}").json()["stats"]
    return [r for r in rows if not name or r["name"] == name]


def _locked():
    pid = sponsor_draft()
    return pid, lock_and_assign(pid, "BGH", "MRC")


# ---------------------------------------------------------------- the plan

def test_calculations_have_no_hardcoded_fields():
    for path in ("ecrf/stats/calculations.py", "ecrf/stats/registry.py", "verification/expected_results.py"):
        text = (ROOT / path).read_text()
        for word in ("Systolic", "Day 1", "Week 12", "PLACEHOLDER", "Diastolic"):
            assert word not in text, f"{word} in {path}"


def test_sap_item_crud_needs_dm(client, demo_accounts):
    pid, dm = _locked()
    item = _endpoint(dm, pid)
    assert item["field"] == SBP and item["kind"] == "endpoint"
    body = {"label": "x", "kind": "endpoint", "field_id": item["field_id"], "baseline_visit_id": "Day 1",
            "analysis_visit_id": "Week 12"}
    for email in (BUILDER, MONITOR, AUDITOR):
        other = site_client(email)
        assert other.post(f"/api/protocols/{pid}/sap", json=body).status_code == 403, email
        assert other.put(f"/api/protocols/{pid}/sap/{item['id']}", json=body).status_code == 403, email
        assert other.delete(f"/api/protocols/{pid}/sap/{item['id']}").status_code == 403, email
        assert other.get(f"/api/protocols/{pid}/sap").status_code == 200, email
    assert site_client(BGH).post(f"/api/protocols/{pid}/sap", json=body).status_code == 403

    assert dm.put(f"/api/protocols/{pid}/sap/{item['id']}", json=body).json()["label"] == "x"
    # What makes no sense is refused, and so is any rule beyond the fixed shape.
    assert dm.post(f"/api/protocols/{pid}/sap", json={**body, "analysis_visit_id": "Day 1"}).status_code == 422
    assert dm.post(f"/api/protocols/{pid}/sap", json={**body, "kind": "survival"}).status_code == 422
    assert dm.post(f"/api/protocols/{pid}/sap", json={**body, "responder_rule": {"on": "change", "op": "in", "value": 1}}).status_code == 422
    assert dm.post(f"/api/protocols/{pid}/sap", json={**body, "analysis_visit_id": "Nowhere"}).status_code == 422
    assert dm.delete(f"/api/protocols/{pid}/sap/{item['id']}").json() == {"deleted": item["id"]}
    assert dm.get(f"/api/protocols/{pid}/sap").json()["items"] == []
    # Each of those is on the form's audit trail.
    rows = dm.get(f"/api/protocols/{pid}/form-history").json()
    assert len([r for r in rows if r["attribute"] == f"sap_item:{item['id']}"]) == 3


# ------------------------------------------------------------ the statistics

def test_descriptive_matches_verifier(client, demo_accounts):
    pid, dm = _locked()
    _changes(pid)
    # Repeats are averaged within a visit first.
    _values(pid, [("BGH-001", "Day 1", SBP, 2, 154)])
    _endpoint(dm, pid)
    st = _stats(dm, pid, "descriptive")[0]
    assert st["status"] == "pass" and st["pass"] is True
    base = st["app"]["baseline"]
    assert base["n"] == 5 and base["mean"] == pytest.approx((152 + 140 + 160 + 130 + 155) / 5)
    assert base["median"] == 152 and base["min"] == 130 and base["max"] == 160
    assert st["app"]["analysis"]["n"] == 4
    assert st["independent"]["baseline"]["sd"] == pytest.approx(base["sd"])


def test_change_from_baseline_matches_verifier_including_ci(client, demo_accounts):
    pid, dm = _locked()
    _changes(pid)
    _endpoint(dm, pid)
    st = _stats(dm, pid, "change_from_baseline")[0]
    assert st["status"] == "pass"
    for side in (st["app"], st["independent"]):
        # Worked by hand. The dropout is excluded, not counted as no change.
        assert side["n"] == 4
        assert side["mean"] == pytest.approx(-13.5)
        assert side["sd"] == pytest.approx(7.188, abs=0.001)
        assert side["ci_low"] == pytest.approx(-24.94, abs=0.01)
        assert side["ci_high"] == pytest.approx(-2.06, abs=0.01)
        assert side["t"] == pytest.approx(-3.756, abs=0.001)
        assert side["p"] == pytest.approx(0.0329, abs=0.0005)


def test_responder_rate_with_wilson_ci(client, demo_accounts):
    pid, dm = _locked()
    _changes(pid)
    item = _endpoint(dm, pid, rule={"on": "change", "op": "<=", "value": -10})
    st = _stats(dm, pid, "responder_rate")[0]
    assert st["status"] == "pass"
    for side in (st["app"], st["independent"]):
        assert (side["responders"], side["n"]) == (3, 4)
        assert side["ci_low"] == pytest.approx(0.3006, abs=0.0005)
        assert side["ci_high"] == pytest.approx(0.9544, abs=0.0005)
    # No rule, no responder rate.
    body = {k: item[k] for k in ("label", "kind", "field_id", "baseline_visit_id", "analysis_visit_id")}
    assert dm.put(f"/api/protocols/{pid}/sap/{item['id']}", json=body).status_code == 200
    assert _stats(dm, pid, "responder_rate") == []


def test_teae_count_uses_first_visit_date(client, demo_accounts):
    pid, dm = _locked()
    _subjects(pid, "BGH", ["BGH-001", "BGH-002", "BGH-003", "BGH-004"])
    _values(pid, [
        ("BGH-001", "Day 1", "Visit date", 1, "2026-01-10"), ("BGH-001", "Week 4", "Visit date", 1, "2026-02-10"),
        ("BGH-001", "Week 4", "AE Start Date", 1, "2026-01-15"),       # after the first visit
        ("BGH-002", "Day 1", "Visit date", 1, "2026-01-10"),
        ("BGH-002", "Day 1", "AE Start Date", 1, "2026-01-05"),        # before it: not emergent
        ("BGH-003", "Day 1", "Visit date", 1, "2026-01-10"),
        ("BGH-003", "Day 1", "AE Start Date", 1, "2026-01-10"),        # on the day counts
        ("BGH-004", "Day 1", "AE Start Date", 1, "2026-03-01"),        # no visit date: cannot say
    ])
    body = {"label": "TEAEs", "kind": "safety", "field_id": _field_id(dm, pid, "Day 1", "AE Start Date")}
    item = dm.post(f"/api/protocols/{pid}/sap", json=body).json()
    st = _stats(dm, pid, "teae_count")[0]
    assert st["status"] == "pass"
    for side in (st["app"], st["independent"]):
        assert side == {"subjects": 2, "denominator": 3, "percent": pytest.approx(200 / 3)}
    # A later baseline visit, such as first dosing, moves the start.
    r = dm.put(f"/api/protocols/{pid}/sap/{item['id']}", json={**body, "baseline_visit_id": "Week 4"})
    assert r.status_code == 200
    st = _stats(dm, pid, "teae_count")[0]
    assert st["status"] == "pass" and st["app"]["subjects"] == 1

    # A safety item points at a date.
    assert dm.post(f"/api/protocols/{pid}/sap", json={**body, "field_id": _field_id(dm, pid, "Day 1", SBP)}).status_code == 422


def test_percent_missing_uses_form_definition(client, demo_accounts):
    pid, dm = _locked()
    _subjects(pid, "BGH", ["BGH-001", "BGH-002", "BGH-003"])
    _values(pid, [("BGH-001", "Day 1", SBP, n, 150) for n in (1, 2, 3)] + [("BGH-001", "Week 12", SBP, 1, 140)])
    _values(pid, [("BGH-002", "Day 1", SBP, 1, 150)], status="submitted")
    _endpoint(dm, pid)
    st = _stats(dm, pid, "percent_missing")[0]
    assert st["status"] == "pass"
    # 3 subjects x (3 readings at each of 2 visits) = 18 slots, 4 approved. BGH-003
    # has no rows at all and BGH-002's value is not approved, and both still count.
    for side in (st["app"], st["independent"]):
        assert side == {"percent": pytest.approx(100 * 14 / 18), "expected": 18, "present": 4}


def test_unsupported_still_refused(client, demo_accounts):
    pid, dm = _locked()
    item = _endpoint(dm, pid)
    with db.session() as s:
        draft = DraftECRF.model_validate(s.scalars(select(ECRFVersion).where(ECRFVersion.protocol_id == pid)
                                                   .order_by(ECRFVersion.version.desc())).first().content)
        analysis = registry.resolve(s.get(SapItem, item["id"]), draft, 0)
        df = registry.load_frame(s, pid)
    with pytest.raises(registry.UnsupportedAnalysis):
        registry.run("breakdown_by_age", df, analysis)
    with pytest.raises(registry.UnsupportedAnalysis):
        registry.run("teae_count", df, analysis)
    with pytest.raises(registry.UnsupportedAnalysis):
        registry.run("responder_rate", df, analysis)
    r = dm.post(f"/api/dashboard/{pid}/unsupported?name=breakdown_by_age")
    assert r.status_code == 403 and "not an approved calculation" in r.json()["detail"]


# ----------------------------------------------------------- dashboard tabs

def test_page_status_counts(client, demo_accounts):
    pid, dm = _locked()
    admin_chain = {"monitor_review_required": False, "investigator_signature_required": True}
    assert site_client("admin@phoenix.demo").put(f"/api/admin/chain/{pid}", json=admin_chain).status_code == 200
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects")
    bgh.post(f"/api/studies/{pid}/subjects")
    site_client(MRC).post(f"/api/studies/{pid}/subjects")
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130)).status_code == 200
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-002", 130)).status_code == 200
    submit(bgh, pid, "BGH-002")

    data = dm.get(f"/api/dashboard/{pid}/page-status").json()
    visits = data["visits"]
    assert data["locked"] is True and visits >= 5
    sites = {x["site"]: x for x in data["sites"]}
    assert sites["BGH"]["expected"] == visits * 2 and sites["MRC"]["expected"] == visits
    rows = {x["code"]: x for x in sites["BGH"]["subjects"]}
    assert rows["BGH-001"]["draft"] == 1 and rows["BGH-001"]["not_started"] == visits - 1
    assert rows["BGH-002"]["submitted"] == 1 and rows["BGH-002"]["needs_approval"] == 1
    assert rows["BGH-002"]["open_queries"] > 0

    ids = [r["id"] for r in dm.get(f"/api/protocols/{pid}/data", params={"site": "BGH"}).json()]
    for q in dm.get("/api/queries").json():
        if q["status"] in ("open", "answered"):
            dm.post(f"/api/queries/{q['id']}/close", json={"reason": "not needed for this test"})
    dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": ids})
    row = next(x for x in dm.get(f"/api/dashboard/{pid}/page-status").json()["sites"][0]["subjects"] if x["code"] == "BGH-002")
    assert (row["approved"], row["needs_signoff"], row["signed"]) == (1, 1, 0)
    pi = site_client(PI)
    assert pi.post(f"/api/protocols/{pid}/signoff", json={"subject_id": "BGH-002", "visit": "Week 4", "password": PASSWORD}).status_code == 200
    row = next(x for x in dm.get(f"/api/dashboard/{pid}/page-status").json()["sites"][0]["subjects"] if x["code"] == "BGH-002")
    assert (row["approved"], row["needs_signoff"], row["signed"]) == (1, 0, 1)
    assert "overdue" not in row


def test_queries_360_by_week(client, demo_accounts):
    pid, dm = _locked()
    bgh = site_client(BGH)
    bgh.post(f"/api/studies/{pid}/subjects")
    bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130))
    submit(bgh, pid, "BGH-001")
    before = dm.get(f"/api/dashboard/{pid}/queries").json()
    assert before["counts"]["open"] > 0 and before["sites"] == ["BGH"]
    assert before["by_site"][0]["site"] == "BGH"

    # Move one query's life back: raised two weeks ago, answered and closed last week.
    now = utcnow()
    with db.session() as s:
        qs = s.scalars(select(Query).where(Query.protocol_id == pid).order_by(Query.id)).all()
        qs[0].raised_at = now - timedelta(days=14)
        qs[0].answered_at = now - timedelta(days=7)
        qs[0].closed_at = now - timedelta(days=7)
        qs[0].status = "closed"
        total = len(qs)
    weeks = dm.get(f"/api/dashboard/{pid}/queries").json()["weeks"]
    assert len(weeks) == 3
    assert (weeks[0]["open"], weeks[0]["closed"]) == (1, 0)
    assert (weeks[1]["answered"] + weeks[1]["closed"]) == 1
    assert weeks[2]["closed"] == 1 and weeks[2]["open"] == total - 1
    assert weeks[0]["week"] < weeks[1]["week"] < weeks[2]["week"]

    # The filters narrow it.
    assert dm.get(f"/api/dashboard/{pid}/queries", params={"raised_by": "person"}).json()["counts"]["open"] == 0
    assert dm.get(f"/api/dashboard/{pid}/queries", params={"raised_by": "system"}).json()["counts"]["closed"] == 1
    assert dm.get(f"/api/dashboard/{pid}/queries", params={"site": "MRC"}).json()["counts"]["open"] == 0


def test_site_dashboard_is_own_site_only(client, demo_accounts):
    pid, dm = _locked()
    _changes(pid, "BGH")
    _changes(pid, "MRC")
    _values(pid, [(f"MRC-00{n}", "Day 1", SBP, 2, 200 + n) for n in range(1, 4)])
    _endpoint(dm, pid)
    whole = _stats(dm, pid, "descriptive")[0]
    assert whole["app"]["baseline"]["n"] == 10 and whole["status"] == "pass"

    for email, n, code in ((BGH, 5, "BGH"), (MRC, 5, "MRC")):
        c = site_client(email)
        dash = c.get(f"/api/dashboard/{pid}").json()
        st = next(x for x in dash["stats"] if x["name"] == "descriptive")
        assert st["app"]["baseline"]["n"] == n and st["status"] == "pass", email
        assert dash["data"]["subjects"] == 5
        assert [x["site"] for x in c.get(f"/api/dashboard/{pid}/page-status").json()["sites"]] == [code]
    assert _stats(site_client(BGH), pid, "percent_missing")[0]["app"]["expected"] == 5 * 6

    # A monitor sees assigned sites only, and read-only sees everything.
    with db.session() as s:
        user = s.scalars(select(User).where(User.email == MONITOR)).one()
        for row in s.scalars(select(MonitorSite).where(MonitorSite.user_id == user.id)):
            s.delete(row)
        s.add(MonitorSite(user_id=user.id, site_org_id=_org_id("MRC"), assigned_by="test"))
    st = _stats(site_client(MONITOR), pid, "descriptive")[0]
    assert st["app"]["baseline"]["n"] == 5 and st["status"] == "pass"
    assert _stats(site_client(AUDITOR), pid, "descriptive")[0]["app"]["baseline"]["n"] == 10


# ---------------------------------------------------------- listing and PDFs

def test_listing_is_scoped_and_export_is_logged(client, demo_accounts):
    pid, dm = _locked()
    bgh, mrc = site_client(BGH), site_client(MRC)
    bgh.post(f"/api/studies/{pid}/subjects")
    mrc.post(f"/api/studies/{pid}/subjects")
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130)).status_code == 200
    assert mrc.post("/api/data/enter", json=entry(pid, "MRC-001", 131)).status_code == 200
    submit(bgh, pid, "BGH-001")
    submit(mrc, pid, "MRC-001")

    pages = dm.get(f"/api/protocols/{pid}/draft").json()["draft"]["forms"]
    form = next(p["form"] for p in pages if p["visit"] == "Week 4")
    assert form in dm.get(f"/api/listing/{pid}").json()["forms"]
    subjects = {r["subject"] for r in dm.get(f"/api/listing/{pid}/{form}").json()["rows"]}
    assert subjects == {"BGH-001", "MRC-001"}
    mine = bgh.get(f"/api/listing/{pid}/{form}").json()
    assert {r["subject"] for r in mine["rows"]} == {"BGH-001"} and SBP in mine["columns"]
    assert mine["rows"][0]["values"][SBP] == "130"
    assert dm.get(f"/api/listing/{pid}/Nothing").status_code == 404

    # Read-only sees the dashboard but neither the listing nor its export.
    for email in (AUDITOR, BUILDER):
        other = site_client(email)
        assert other.get(f"/api/listing/{pid}/{form}").status_code == 403
        assert other.get(f"/api/listing/{pid}/{form}/export").status_code == 403

    r = bgh.get(f"/api/listing/{pid}/{form}/export")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "BGH-001" in r.text and "MRC-001" not in r.text and SBP in r.text.splitlines()[0]
    with db.session() as s:
        rows = s.scalars(select(UserAccessEvent).where(UserAccessEvent.action == "export")).all()
        assert len(rows) == 1 and rows[0].by == BGH and form in rows[0].detail


def test_blank_pdf_renders_and_contains_every_field(client, demo_accounts):
    pid = sponsor_draft()
    builder = site_client(BUILDER)
    assert builder.get(f"/api/protocols/{pid}/pdf/blank").status_code == 409, "only a locked form has a blank eCRF"
    dm = lock_and_assign(pid, "BGH")
    assert site_client(AUDITOR).get(f"/api/protocols/{pid}/pdf/blank").status_code == 200
    r = builder.get(f"/api/protocols/{pid}/pdf/blank")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and r.headers["content-type"] == "application/pdf"
    with pdfplumber.open(io.BytesIO(r.content)) as doc:
        pages = [p.extract_text() or "" for p in doc.pages]
    text = " ".join(" ".join(pages).split())
    draft = dm.get(f"/api/protocols/{pid}/draft").json()
    fields = [(form["visit"], f) for form in draft["draft"]["forms"] for f in form["fields"] if f["collected"]]
    assert fields
    for _, f in fields:
        assert f["name"] in text, f["name"]
    assert "PHX-401-201" in pages[0] and f"version {draft['version']}" in pages[0] and "locked" in pages[0]
    assert "Page 1" in pages[0] and f"Page {len(pages)}" in pages[-1]
    # One page per visit at the least, each starting with its visit.
    visits = list(dict.fromkeys(form["visit"] for form in draft["draft"]["forms"]))
    assert len(pages) >= len(visits)
    for visit in visits:
        assert any(p.splitlines()[1:2] == [visit] for p in pages), visit
    # A field's code and a protocol quote are both there, in small type.
    model_field = next(f for _, f in fields if f["origin"] == "model" and f["cdash"])
    assert f"CDASH {model_field['cdash']}" in text
    assert " ".join(model_field["source"]["quote"].split())[:30] in text


def test_casebook_pdf_contains_signoff_block(client, demo_accounts):
    pid, dm = _locked()
    site_client("admin@phoenix.demo").put(f"/api/admin/chain/{pid}", json={"monitor_review_required": False,
                                                                           "investigator_signature_required": True})
    bgh = site_client(BGH)
    subject = bgh.post(f"/api/studies/{pid}/subjects").json()
    assert bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130)).status_code == 200
    submit(bgh, pid, "BGH-001")

    def text(c):
        r = c.get(f"/api/subjects/{subject['id']}/pdf")
        assert r.status_code == 200 and r.content[:4] == b"%PDF", r.text[:100]
        with pdfplumber.open(io.BytesIO(r.content)) as doc:
            return " ".join(" ".join((p.extract_text() or "") for p in doc.pages).split())

    t = text(bgh)
    assert "Casebook: BGH-001" in t and SBP.split()[0] in t and "130" in t and "Open query" in t
    assert "Investigator sign-off: not signed." in t and "Signed by" not in t

    # Scoped like the listing.
    assert site_client(MRC).get(f"/api/subjects/{subject['id']}/pdf").status_code == 404
    assert site_client(AUDITOR).get(f"/api/subjects/{subject['id']}/pdf").status_code == 403
    assert site_client(BUILDER).get(f"/api/subjects/{subject['id']}/pdf").status_code == 403

    for q in dm.get("/api/queries").json():
        if q["status"] in ("open", "answered"):
            dm.post(f"/api/queries/{q['id']}/close", json={"reason": "not needed for this test"})
    ids = [r["id"] for r in dm.get(f"/api/protocols/{pid}/data").json()]
    dm.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": ids})
    assert site_client(PI).post(f"/api/protocols/{pid}/signoff", json={
        "subject_id": "BGH-001", "visit": "Week 4", "password": PASSWORD}).status_code == 200
    t = text(dm)
    assert f"signed by {PI}" in t and "complete and accurate" in t
    assert "approved" in t and "Open query" not in t
