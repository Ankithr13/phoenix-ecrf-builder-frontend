"""A monitor sees a protocol only where one of their assigned sites takes part.

The demo monitor is assigned Boston General (BGH) and not Mercy (MRC)."""

from conftest import APPROVER, AUDITOR, BUILDER, MONITOR
from sqlalchemy import select
from test_lock_sites_data import _org_id, lock_and_assign, site_client, sponsor_draft

from ecrf.storage import db
from ecrf.storage.models import Notification, Protocol, ProtocolSite, User


def _other_protocol(name: str, *sites: str) -> int:
    """A second protocol on the same sponsor, assigned to the given sites.
    The sample loads once per sponsor, so this one is written directly."""
    with db.session() as s:
        sponsor = s.scalars(select(Protocol)).first().org_id
        p = Protocol(org_id=sponsor, name=name, filename=f"{name}.pdf", text_hash=name, normalised="",
                     sections=[], pages=1, tokens_estimate=0, uploaded_by=BUILDER)
        s.add(p)
        s.flush()
        for code in sites:
            s.add(ProtocolSite(protocol_id=p.id, site_org_id=_org_id(code), assigned_by=APPROVER))
        s.commit()
        return p.id


def _notify_monitor(pid: int) -> int:
    with db.session() as s:
        cra = s.scalars(select(User).where(User.email == MONITOR)).first()
        n = Notification(user_id=cra.id, kind="visit_submitted", protocol_id=pid, body="test")
        s.add(n)
        s.commit()
        return n.id


def test_monitor_sees_only_protocols_with_their_sites(client, demo_accounts):
    mine = sponsor_draft()
    lock_and_assign(mine, "BGH")
    mercy = _other_protocol("Mercy only", "MRC")
    nobody = _other_protocol("No sites yet")
    both = _other_protocol("Both sites", "BGH", "MRC")

    monitor = site_client(MONITOR)
    assert sorted(p["id"] for p in monitor.get("/api/protocols").json()) == sorted([mine, both])
    # Other roles are unchanged: the data manager and read only see all four.
    for email in (APPROVER, AUDITOR):
        assert sorted(p["id"] for p in site_client(email).get("/api/protocols").json()) == sorted(
            [mine, mercy, nobody, both])

    # The inbox follows the same scope.
    _notify_monitor(mine)
    hidden = _notify_monitor(mercy)
    assert {n["protocol_id"] for n in monitor.get("/api/notifications").json()} == {mine}
    assert monitor.get(f"/api/notifications?protocol_id={mercy}").json() == []
    assert monitor.get("/api/notifications/unread-count").json() == {"unread": 1}
    assert monitor.post(f"/api/notifications/{hidden}/read").status_code == 404
    assert monitor.post("/api/notifications/read-all").json() == {"read": 1}


def test_monitor_gets_404_on_protocol_without_their_sites(client, demo_accounts):
    pid = sponsor_draft()
    dm = lock_and_assign(pid, "MRC")
    monitor = site_client(MONITOR)
    routes = [
        f"/api/protocols/{pid}/draft",           # Review page
        f"/api/protocols/{pid}/versions",
        f"/api/dashboard/{pid}",                 # Dashboard
        f"/api/dashboard/{pid}/queries",
        f"/api/dashboard/{pid}/page-status",
        f"/api/protocols/{pid}/sap",
        f"/api/protocols/{pid}/data",            # Data review
        f"/api/protocols/{pid}/pdf/blank",       # PDFs
        f"/api/listing/{pid}",
    ]
    for url in routes:
        assert monitor.get(url).status_code == 404, url
        assert dm.get(url).status_code == 200, url
    assert monitor.get(f"/api/notifications?protocol_id={pid}").json() == []
    # A query on it cannot be raised either.
    assert monitor.post("/api/queries", json={"protocol_id": pid, "text": "?"}).status_code == 404
    assert pid not in {q["protocol_id"] for q in monitor.get("/api/queries").json()}
    # A protocol with no sites at all is out of scope too.
    bare = _other_protocol("No sites yet")
    assert monitor.get(f"/api/protocols/{bare}/draft").status_code == 404
    assert monitor.get(f"/api/dashboard/{bare}").status_code == 404


def test_monitor_sees_protocol_after_their_site_is_assigned(client, demo_accounts):
    pid = sponsor_draft()
    dm = lock_and_assign(pid, "MRC")
    monitor = site_client(MONITOR)
    assert pid not in {p["id"] for p in monitor.get("/api/protocols").json()}
    assert monitor.get(f"/api/dashboard/{pid}").status_code == 404

    assert dm.post(f"/api/protocols/{pid}/sites", json={"site_org_id": _org_id("BGH")}).status_code == 200
    assert pid in {p["id"] for p in monitor.get("/api/protocols").json()}
    assert monitor.get(f"/api/dashboard/{pid}").status_code == 200
    assert monitor.get(f"/api/protocols/{pid}/draft").status_code == 200

    # And it goes again when the site is taken off.
    assert dm.delete(f"/api/protocols/{pid}/sites/{_org_id('BGH')}").status_code == 200
    assert monitor.get(f"/api/dashboard/{pid}").status_code == 404
