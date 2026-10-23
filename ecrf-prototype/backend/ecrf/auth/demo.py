"""The demo organisations and accounts. Idempotent, used by
scripts/seed_demo.py and by the test fixtures."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth.passwords import hash_password
from ecrf.config import config
from ecrf.storage.models import Organisation, User

ORGS = [
    ("Phoenix Clinical Demo", "sponsor", "PHX"),
    ("Boston General Demo", "site", "BGH"),
    ("Mercy Hospital Demo", "site", "MRC"),
]
USERS = [
    ("builder@phoenix.demo", "Dana Builder", "PHX", "builder"),
    ("approver@phoenix.demo", "Alex Approver", "PHX", "approver"),
    ("staff@bgh.demo", "Sam Site", "BGH", "site_staff"),
    ("staff@mrc.demo", "Morgan Site", "MRC", "site_staff"),
]


def seed(s: Session, password: str | None = None) -> list[User]:
    password = password or config.demo_password
    orgs: dict[str, Organisation] = {}
    for name, typ, code in ORGS:
        org = s.scalars(select(Organisation).where(Organisation.code == code)).first()
        if org is None:
            org = Organisation(name=name, type=typ, code=code)
            s.add(org)
            s.flush()
        orgs[code] = org
    users = []
    for email, name, code, role in USERS:
        u = s.scalars(select(User).where(User.email == email)).first()
        if u is None:
            u = User(email=email, name=name, org_id=orgs[code].id, role=role,
                     password_hash=hash_password(password), is_active=True)
            s.add(u)
        else:
            u.name, u.org_id, u.role = name, orgs[code].id, role
            u.password_hash = hash_password(password)
        users.append(u)
    s.flush()
    return users
