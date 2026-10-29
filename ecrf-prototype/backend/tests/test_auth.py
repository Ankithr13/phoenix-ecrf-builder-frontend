"""Login, sessions, and the ways they end."""

from datetime import timedelta

from conftest import BGH, BUILDER, PASSWORD, login
from sqlalchemy import select

from ecrf.storage import db
from ecrf.storage.models import User, UserSession, utcnow


def test_login_succeeds_and_me_reflects_the_account(client, demo_accounts):
    me = login(client, BUILDER)
    assert me["org"]["type"] == "sponsor" and me["role"] == "sponsor"
    assert "protocol.upload" in me["permissions"] and "form.lock" in me["permissions"]
    assert client.get("/api/auth/me").json()["user"]["email"] == BUILDER
    assert client.cookies.get("ecrf_session")


def test_login_fails_with_one_message_for_every_reason(client, demo_accounts):
    wrong = client.post("/api/auth/login", json={"email": BUILDER, "password": "nope"})
    unknown = client.post("/api/auth/login", json={"email": "ghost@phoenix.demo", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"] == "Email or password is incorrect"
    assert "ecrf_session" not in client.cookies


def test_logged_out_requests_get_401(client, demo_accounts):
    assert client.get("/api/protocols").status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/health").status_code == 200, "health stays open"


def test_disabled_user_cannot_log_in_or_keep_a_session(client, demo_accounts):
    login(client, BGH)
    with db.session() as s:
        s.scalars(select(User).where(User.email == BGH)).first().is_active = False
    assert client.get("/api/auth/me").status_code == 401, "live session refused once disabled"
    r = client.post("/api/auth/login", json={"email": BGH, "password": PASSWORD})
    assert r.status_code == 401 and r.json()["detail"] == "Email or password is incorrect"


def test_session_expires(client, demo_accounts):
    login(client, BUILDER)
    with db.session() as s:
        row = s.scalars(select(UserSession)).first()
        row.expires_at = utcnow() - timedelta(seconds=1)
    assert client.get("/api/auth/me").status_code == 401


def test_logout_revokes_the_session(client, demo_accounts):
    login(client, BUILDER)
    saved = client.cookies.get("ecrf_session")
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    # Replaying the old cookie must not work either: the row is revoked.
    client.cookies.set("ecrf_session", saved)
    assert client.get("/api/auth/me").status_code == 401
    with db.session() as s:
        assert s.scalars(select(UserSession)).first().revoked_at is not None


def test_five_failures_in_a_row_lock_the_email_out(client, demo_accounts):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": BUILDER, "password": "x"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": BUILDER, "password": PASSWORD}).status_code == 429


def test_email_is_case_insensitive(client, demo_accounts):
    assert login(client, "Dana@Phoenix.Demo")["user"]["email"] == BUILDER
