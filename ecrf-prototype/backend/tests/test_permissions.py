"""The permission table, every role against the endpoints, cross-organisation
access, and the route walks."""

import pytest
from conftest import (
    ADMIN,
    APPROVER,
    AUDITOR,
    BGH,
    BUILDER,
    ENTRY,
    MONITOR,
    MRC,
    PASSWORD,
    PI,
    fresh_client,
    login,
)
from fastapi.routing import APIRoute
from test_lock_sites_data import _org_id, entry, lock_and_assign, site_client, sponsor_draft

from ecrf.api.app import ROUTERS
from ecrf.auth.passwords import hash_password
from ecrf.auth.permissions import PERMISSIONS
from ecrf.storage import db
from ecrf.storage.models import Organisation, User

R = ("admin", "builder", "data_manager", "monitor", "investigator", "site_coordinator", "site_data_entry", "read_only")

# The agreed matrix, one row per line as it appears in SPRINT3.md.
TABLE = {
    #                        adm bld dm  mon inv crc ent ro
    "protocol.upload":      "0   1   0   0   0   0   0   0",
    "protocol.extract":     "0   1   0   0   0   0   0   0",
    "form.edit":            "0   1   0   0   0   0   0   0",
    "protocol.lock":        "0   0   1   0   0   0   0   0",
    "protocol.view":        "1   1   1   1   1   1   1   1",
    "sites.assign":         "1   0   1   0   0   0   0   0",
    "subject.create":       "0   0   0   0   0   1   0   0",
    "data.enter":           "0   0   0   0   1   1   1   0",
    "data.submit":          "0   0   0   0   1   1   1   0",
    "data.approve":         "0   0   1   0   0   0   0   0",
    "data.monitor_review":  "0   0   0   1   0   0   0   0",
    "query.raise":          "0   0   1   1   1   1   0   0",
    "query.answer":         "0   0   0   0   1   1   1   0",
    "query.close":          "0   0   1   1   0   0   0   0",
    "signoff.sign":         "0   0   0   0   1   0   0   0",
    "dashboard.view":       "1   1   1   1   1   1   0   1",
    "listing.view":         "0   0   1   1   1   1   0   0",
    "listing.export":       "0   0   1   1   1   1   0   0",
    "report.pdf":           "0   1   1   1   1   1   0   1",
    "sap.edit":             "0   0   1   0   0   0   0   0",
    "users.manage":         "1   0   0   0   0   0   0   0",
    "roles.assign":         "1   0   0   0   0   0   0   0",
    "chain.configure":      "1   0   0   0   0   0   0   0",
    "study.lock":           "1   0   1   0   0   0   0   0",
}


def test_matrix():
    expected = {role: set() for role in R}
    for perm, row in TABLE.items():
        for role, cell in zip(R, row.split(), strict=True):
            if cell == "1":
                expected[role].add(perm)
    assert {role: set(perms) for role, perms in PERMISSIONS.items()} == expected


ENTRY_BODY = {"subject_id": "S1", "visit": "Week 4",
              "readings": [{"field_name": "Systolic Blood Pressure", "value": 120}]}
WHO = {"builder": BUILDER, "dm": APPROVER, "crc": BGH, "anon": None}

# method, path, body, expected for builder / data manager / site coordinator / anon
ROUTES = [
    ("GET", "/api/protocols", None, 200, 200, 200, 401),
    ("POST", "/api/protocols/sample", None, 200, 403, 403, 401),
    ("POST", "/api/protocols/{id}/extract", None, 200, 403, 403, 401),
    ("GET", "/api/protocols/{id}/draft", None, 200, 200, 404, 401),
    ("GET", "/api/protocols/{id}/versions", None, 200, 200, 404, 401),
    ("GET", "/api/protocols/{id}/section/7.3.2", None, 200, 200, 404, 401),
    ("POST", "/api/protocols/{id}/review", {"changes": []}, 200, 403, 403, 401),
    ("POST", "/api/data/validate", ENTRY_BODY, 403, 403, 404, 401),
    ("POST", "/api/data/enter", ENTRY_BODY, 403, 403, 404, 401),
    # refused on state: the sample is extracted but not locked
    ("POST", "/api/data/seed/{id}", None, 403, 409, 403, 401),
    ("GET", "/api/data/{id}/subjects", None, 403, 200, 404, 401),
    ("GET", "/api/dashboard/calculations", None, 200, 200, 200, 401),
    ("GET", "/api/dashboard/{id}", None, 200, 200, 404, 401),
    ("POST", "/api/dashboard/{id}/unsupported?name=x", None, 403, 403, 403, 401),
    ("GET", "/api/studies", None, 403, 403, 200, 401),
    ("POST", "/api/protocols/{id}/lock", None, 403, 409, 403, 401),
    ("GET", "/api/protocols/{id}/sites", None, 200, 200, 403, 401),
    ("POST", "/api/protocols/{id}/sites", {"site_org_id": 1}, 403, 409, 403, 401),
    ("GET", "/api/protocols/{id}/data", None, 403, 200, 404, 401),
    ("POST", "/api/protocols/{id}/data/approve", {"observation_ids": []}, 403, 200, 403, 401),
    ("GET", "/api/studies/{id}/subjects", None, 403, 200, 404, 401),
    ("POST", "/api/studies/{id}/subjects", None, 403, 403, 404, 401),
    ("GET", "/api/queries", None, 403, 200, 200, 401),
    ("POST", "/api/data/999999/queries", {"text": "why"}, 403, 404, 404, 401),
    ("POST", "/api/queries/999999/answer", {"text": "because"}, 403, 404, 404, 401),
    ("POST", "/api/queries/999999/close", None, 403, 404, 403, 401),
    ("GET", "/api/admin/users", None, 403, 403, 403, 401),
    ("GET", "/api/auth/me", None, 200, 200, 200, 401),
]


@pytest.fixture
def sample_protocol(client, demo_accounts):
    """A protocol owned by the demo sponsor, extracted once."""
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    assert client.post(f"/api/protocols/{pid}/extract").status_code == 200
    client.post("/api/auth/logout")
    return pid


@pytest.mark.parametrize("who", list(WHO))
@pytest.mark.parametrize("method,path,body,bl,dm,crc,anon", ROUTES, ids=[f"{m} {p}" for m, p, *_ in ROUTES])
def test_routes_by_role(sample_protocol, who, method, path, body, bl, dm, crc, anon):
    expected = {"builder": bl, "dm": dm, "crc": crc, "anon": anon}[who]
    c = fresh_client()
    with c:
        if WHO[who]:
            login(c, WHO[who])
        url = path.replace("{id}", str(sample_protocol))
        if body is not None and "protocol_id" not in body and url.startswith("/api/data/"):
            body = {**body, "protocol_id": sample_protocol}
        r = c.request(method, url, json=body)
        assert r.status_code == expected, f"{who} {method} {url}: {r.status_code} {r.text[:120]}"


def _routes():
    return [rt for router in ROUTERS for rt in router.routes if isinstance(rt, APIRoute)]


def _dep_names(dep) -> list[str]:
    out = []
    for d in dep.dependencies:
        out.append(getattr(d.call, "__qualname__", str(d.call)))
        out += _dep_names(d)
    return out


def test_every_router_route_declares_a_permission():
    """Login and logout are the only open routes; /me and change-password
    need a signed-in user and no more."""
    open_routes = []
    for rt in _routes():
        names = _dep_names(rt.dependant)
        if not any(n.startswith("require") or n == "current_user" for n in names):
            open_routes.append(rt.path)
    assert sorted(open_routes) == ["/api/auth/login", "/api/auth/logout"]
    only_signed_in = [rt.path for rt in _routes()
                      if "current_user" in _dep_names(rt.dependant)]
    assert sorted(only_signed_in) == ["/api/auth/change-password", "/api/auth/me"]


def test_read_only_has_no_write_route(client, demo_accounts):
    login(client, AUDITOR)
    walked = 0
    for rt in _routes():
        if rt.path in ("/api/auth/login", "/api/auth/logout", "/api/auth/change-password"):
            continue  # one's own session and password, not study data
        for method in rt.methods - {"GET", "HEAD", "OPTIONS"}:
            url = rt.path
            for name in ("protocol_id", "user_id", "observation_id", "query_id", "site_org_id"):
                url = url.replace("{" + name + "}", "1")
            r = client.request(method, url, params={"name": "x"})
            assert r.status_code == 403, f"{method} {url}: {r.status_code} {r.text[:100]}"
            walked += 1
    assert walked > 20


def test_read_only_can_read_dashboards(client, demo_accounts):
    pid = sponsor_draft()
    login(client, AUDITOR)
    assert client.get(f"/api/dashboard/{pid}").status_code == 200
    assert client.get(f"/api/protocols/{pid}/draft").status_code == 200
    assert client.get(f"/api/protocols/{pid}/data").status_code == 403


def test_site_data_entry_cannot_create_subject(client, demo_accounts):
    pid = sponsor_draft()
    lock_and_assign(pid, "BGH")
    entry_clerk = site_client(ENTRY)
    assert entry_clerk.post(f"/api/studies/{pid}/subjects").status_code == 403
    assert site_client(PI).post(f"/api/studies/{pid}/subjects").status_code == 403
    assert site_client(BGH).post(f"/api/studies/{pid}/subjects").json()["code"] == "BGH-001"
    assert entry_clerk.post("/api/data/enter", json=entry(pid, "BGH-001", 130)).status_code == 200
    assert entry_clerk.post(f"/api/data/{1}/queries", json={"text": "?"}).status_code == 403


def test_builder_cannot_lock_and_dm_cannot_edit_form(client, demo_accounts):
    pid = sponsor_draft()
    builder, dm = site_client(BUILDER), site_client(APPROVER)
    assert builder.post(f"/api/protocols/{pid}/lock").status_code == 403
    assert dm.post(f"/api/protocols/{pid}/review", json={"changes": []}).status_code == 403
    assert dm.post(f"/api/protocols/{pid}/extract").status_code == 403


def test_monitor_sees_only_assigned_sites(client, demo_accounts):
    """The demo monitor is assigned Boston General and not Mercy."""
    pid = sponsor_draft()
    dm = lock_and_assign(pid, "BGH", "MRC")
    bgh, mrc = site_client(BGH), site_client(MRC)
    bgh.post(f"/api/studies/{pid}/subjects")
    mrc.post(f"/api/studies/{pid}/subjects")
    bgh.post("/api/data/enter", json=entry(pid, "BGH-001", 130))
    mrc.post("/api/data/enter", json=entry(pid, "MRC-001", 131))
    rows = {r["site"]: r for r in dm.get(f"/api/protocols/{pid}/data").json()}
    assert set(rows) == {"BGH", "MRC"}

    monitor = site_client(MONITOR)
    assert [r["site"] for r in monitor.get(f"/api/protocols/{pid}/data").json()] == ["BGH"]
    assert [r["code"] for r in monitor.get(f"/api/studies/{pid}/subjects").json()] == ["BGH-001"]
    assert monitor.post(f"/api/data/{rows['MRC']['id']}/queries", json={"text": "?"}).status_code == 404
    assert monitor.post(f"/api/data/{rows['BGH']['id']}/queries", json={"text": "?"}).status_code == 200
    mrc_q = dm.post(f"/api/data/{rows['MRC']['id']}/queries", json={"text": "?"}).json()
    assert all(q["site"] == "BGH" for q in monitor.get("/api/queries").json())
    assert monitor.post(f"/api/queries/{mrc_q['id']}/close").status_code == 404
    assert monitor.post(f"/api/protocols/{pid}/data/approve", json={"observation_ids": []}).status_code == 403


def test_another_sponsor_cannot_see_phoenix_protocols(client, sample_protocol):
    with db.session() as s:
        other = Organisation(name="Other Sponsor", type="sponsor", code="OTH")
        s.add(other)
        s.flush()
        for email, role in (("b@other.demo", "builder"), ("dm@other.demo", "data_manager")):
            s.add(User(email=email, name="Other Sponsor", org_id=other.id, role=role,
                       password_hash=hash_password(PASSWORD), is_active=True))
    c = fresh_client()
    with c:
        login(c, "b@other.demo")
        assert c.get("/api/protocols").json() == []
        for url in (f"/api/protocols/{sample_protocol}/draft",
                    f"/api/protocols/{sample_protocol}/versions",
                    f"/api/dashboard/{sample_protocol}"):
            assert c.get(url).status_code == 404, url
        assert c.post(f"/api/protocols/{sample_protocol}/review", json={"changes": []}).status_code == 404
        assert c.post(f"/api/protocols/{sample_protocol}/extract").status_code == 404
        # And their own copy of the sample is a separate protocol.
        assert c.post("/api/protocols/sample").json()["id"] != sample_protocol
    d = fresh_client()
    with d:
        login(d, "dm@other.demo")
        assert d.get(f"/api/data/{sample_protocol}/subjects").status_code == 404
    a = fresh_client()
    with a:
        login(a, ADMIN)
        assert all(u["org"]["code"] != "OTH" for u in a.get("/api/admin/users").json()), "admins stay in their own org"
    assert _org_id("OTH")
