"""The demo organisations and accounts. Idempotent, used by
scripts/seed_demo.py and by the test fixtures."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecrf.auth.passwords import hash_password
from ecrf.config import config
from ecrf.storage.models import MonitorSite, Organisation, User

ORGS = [
    ("Phoenix Clinical Demo", "sponsor", "PHX"),
    ("Boston General Demo", "site", "BGH"),
    ("Mercy Hospital Demo", "site", "MRC"),
]
# One person per role. The monitor is assigned Boston General only, so the
# scoping is visible on a demo: Mercy's data is hidden from them.
USERS = [
    ("admin@phoenix.demo", "Priya Admin", "PHX", "admin"),
    ("builder@phoenix.demo", "Ben Builder", "PHX", "builder"),
    ("dm@phoenix.demo", "Dana Patel", "PHX", "data_manager"),
    ("cra@phoenix.demo", "Casey Monitor", "PHX", "monitor"),
    ("auditor@phoenix.demo", "Alex Auditor", "PHX", "read_only"),
    ("pi@bgh.demo", "Dr Lee", "BGH", "investigator"),
    ("crc@bgh.demo", "Sam Coordinator", "BGH", "site_coordinator"),
    ("entry@bgh.demo", "Jo Entry", "BGH", "site_data_entry"),
    ("crc@mrc.demo", "Morgan Coordinator", "MRC", "site_coordinator"),
]
MONITOR_SITES = {"cra@phoenix.demo": ("BGH",)}


def seed(s: Session, password: str | None = None, missing_only: bool = False) -> list[User]:
    """Create the demo accounts. Existing ones are reset to the demo role and
    password, unless missing_only, which only adds those not there yet."""
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
        elif not missing_only:
            u.name, u.org_id, u.role = name, orgs[code].id, role
            u.password_hash = hash_password(password)
        users.append(u)
    s.flush()
    for u in users:
        for code in MONITOR_SITES.get(u.email, ()):
            if not s.scalars(select(MonitorSite).where(MonitorSite.user_id == u.id,
                                                        MonitorSite.site_org_id == orgs[code].id)).first():
                s.add(MonitorSite(user_id=u.id, site_org_id=orgs[code].id, assigned_by="seed"))
    s.flush()
    return users
