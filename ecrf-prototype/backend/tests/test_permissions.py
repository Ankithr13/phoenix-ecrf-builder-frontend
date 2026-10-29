"""Every role against every endpoint, plus cross-organisation access.

200 means allowed, 401 no session, 403 wrong role, 404 outside the
caller's scope (which is what a site gets for a sponsor's protocol)."""

import pytest
from conftest import BGH, BUILDER, PASSWORD, fresh_client, login

from ecrf.auth.passwords import hash_password
from ecrf.storage import db
from ecrf.storage.models import Organisation, User

ROLES = {"sponsor": BUILDER, "site_staff": BGH, "anon": None}

ENTRY = {"subject_id": "S1", "visit": "Week 4",
         "readings": [{"field_name": "Systolic Blood Pressure", "value": 120}]}

# method, path, body, expected for sponsor / site_staff / anon
MATRIX = [
    ("GET", "/api/protocols", None, 200, 403, 401),
    ("POST", "/api/protocols/sample", None, 200, 403, 401),
    ("POST", "/api/protocols/{id}/extract", None, 200, 403, 401),
    ("GET", "/api/protocols/{id}/draft", None, 200, 404, 401),
    ("GET", "/api/protocols/{id}/versions", None, 200, 404, 401),
    ("GET", "/api/protocols/{id}/section/7.3.2", None, 200, 404, 401),
    ("POST", "/api/protocols/{id}/review", {"changes": []}, 200, 403, 401),
    ("POST", "/api/data/validate", ENTRY, 403, 404, 401),
    ("POST", "/api/data/enter", ENTRY, 403, 404, 401),
    ("POST", "/api/data/seed/{id}", None, 200, 403, 401),
    ("GET", "/api/data/{id}/subjects", None, 200, 404, 401),
    ("GET", "/api/dashboard/calculations", None, 200, 403, 401),
    ("GET", "/api/dashboard/{id}", None, 200, 403, 401),
    ("POST", "/api/dashboard/{id}/unsupported?name=x", None, 403, 403, 401),
    ("GET", "/api/studies", None, 403, 200, 401),
    # stage 3. The sample is extracted but not locked, so the sponsor's lock
    # and site assignment are refused on state, not on role.
    ("POST", "/api/protocols/{id}/lock", None, 409, 403, 401),
    ("GET", "/api/protocols/{id}/sites", None, 200, 403, 401),
    ("POST", "/api/protocols/{id}/sites", {"site_org_id": 1}, 409, 403, 401),
    ("GET", "/api/protocols/{id}/data", None, 200, 404, 401),
    ("POST", "/api/protocols/{id}/data/approve", {"observation_ids": []}, 200, 403, 401),
    ("GET", "/api/studies/{id}/subjects", None, 200, 404, 401),
    ("POST", "/api/studies/{id}/subjects", None, 403, 404, 401),
    # stage 5
    ("GET", "/api/queries", None, 200, 200, 401),
    ("POST", "/api/data/999999/queries", {"text": "why"}, 404, 403, 401),
    ("POST", "/api/queries/999999/answer", {"text": "because"}, 403, 404, 401),
    ("POST", "/api/queries/999999/close", None, 404, 403, 401),
    ("GET", "/api/auth/me", None, 200, 200, 401),
]


@pytest.fixture
def sample_protocol(client, demo_accounts):
    """A protocol owned by the demo sponsor, extracted once."""
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    assert client.post(f"/api/protocols/{pid}/extract").status_code == 200
    client.post("/api/auth/logout")
    return pid


@pytest.mark.parametrize("role", list(ROLES))
@pytest.mark.parametrize("method,path,body,sp,st,anon", MATRIX,
                         ids=[f"{m} {p}" for m, p, *_ in MATRIX])
def test_matrix(sample_protocol, role, method, path, body, sp, st, anon):
    expected = {"sponsor": sp, "site_staff": st, "anon": anon}[role]
    c = fresh_client()
    with c:
        if ROLES[role]:
            login(c, ROLES[role])
        url = path.replace("{id}", str(sample_protocol))
        if body is not None and "protocol_id" not in body and url.startswith("/api/data/"):
            body = {**body, "protocol_id": sample_protocol}
        r = c.request(method, url, json=body)
        assert r.status_code == expected, f"{role} {method} {url}: {r.status_code} {r.text[:120]}"


def test_another_sponsor_cannot_see_phoenix_protocols(client, sample_protocol):
    with db.session() as s:
        other = Organisation(name="Other Sponsor", type="sponsor", code="OTH")
        s.add(other)
        s.flush()
        s.add(User(email="b@other.demo", name="Other Sponsor", org_id=other.id, role="sponsor",
                   password_hash=hash_password(PASSWORD), is_active=True))
    c = fresh_client()
    with c:
        login(c, "b@other.demo")
        assert c.get("/api/protocols").json() == []
        for url in (f"/api/protocols/{sample_protocol}/draft",
                    f"/api/protocols/{sample_protocol}/versions",
                    f"/api/dashboard/{sample_protocol}",
                    f"/api/data/{sample_protocol}/subjects"):
            assert c.get(url).status_code == 404, url
        r = c.post(f"/api/protocols/{sample_protocol}/review", json={"changes": []})
        assert r.status_code == 404
        r = c.post(f"/api/protocols/{sample_protocol}/extract")
        assert r.status_code == 404
        # And their own copy of the sample is a separate protocol.
        assert c.post("/api/protocols/sample").json()["id"] != sample_protocol
