"""Create the demo organisations and accounts. Idempotent.

    python scripts/seed_demo.py            create or update the demo accounts
    python scripts/seed_demo.py --missing   only add accounts that do not exist yet

The password comes from DEMO_PASSWORD (default demo1234) and is printed
once. In production this does nothing unless SEED_DEMO=1. There is no sign-up page on purpose: accounts are provisioned, the
way invite-only business tools work."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecrf.auth.demo import seed
from ecrf.config import config
from ecrf.storage import db


def main() -> None:
    if config.env == "prod" and not config.seed_demo:
        print("ECRF_ENV=prod: demo accounts are created only when SEED_DEMO=1")
        return
    if config.env == "prod" and config.demo_password == "demo1234":
        print("ECRF_ENV=prod: set DEMO_PASSWORD; the default password is for development only")
        return
    with db.session() as s:
        users = seed(s, missing_only="--missing" in sys.argv)
        rows = [(u.email, u.role) for u in users]
    print("Demo accounts ready. Password for all of them:", config.demo_password)
    for email, role in rows:
        print(f"  {email:<26} {role}")


if __name__ == "__main__":
    main()
