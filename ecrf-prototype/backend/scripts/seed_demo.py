"""Create the demo organisations and accounts. Idempotent.

    python scripts/seed_demo.py            create or update the demo accounts
    python scripts/seed_demo.py --if-empty only when the user table is empty

The password comes from DEMO_PASSWORD (default demo1234) and is printed
once. There is no sign-up page on purpose: accounts are provisioned, the
way invite-only business tools work."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from ecrf.auth.demo import seed
from ecrf.config import config
from ecrf.storage import db
from ecrf.storage.models import User


def main() -> None:
    with db.session() as s:
        if "--if-empty" in sys.argv and s.scalars(select(User)).first() is not None:
            return
        users = seed(s)
        rows = [(u.email, u.role) for u in users]
    print("Demo accounts ready. Password for all of them:", config.demo_password)
    for email, role in rows:
        print(f"  {email:<26} {role}")


if __name__ == "__main__":
    main()
