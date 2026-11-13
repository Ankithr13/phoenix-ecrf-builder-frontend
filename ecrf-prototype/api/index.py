"""Vercel's entry point for the backend.

vercel.json rewrites every /api/* request here. FastAPI still sees the
original path, so the routes are the same as under uvicorn. The frontend is
served by Vercel as static files from the same domain, so the session cookie
needs no cross-site settings.
"""

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

if not os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql")):
    # Without it the app would open a SQLite file inside the deployment, which
    # is read-only and separate for every instance.
    raise RuntimeError("Set DATABASE_URL in the Vercel project to the Supabase transaction pooler URL")
# Only /tmp is writable on Vercel. Uploaded PDFs are read into the database
# straight away, so losing this folder when an instance stops loses nothing.
os.environ.setdefault("ECRF_UPLOAD_DIR", "/tmp/ecrf-uploads")

from ecrf.api.app import app  # noqa: E402
from ecrf.config import check_production, config  # noqa: E402
from ecrf.storage import db, migrate  # noqa: E402

# The same checks the app's startup runs, in case the platform skips startup
# events. A schema behind the code fails here, with the command that fixes it.
check_production(config)
migrate.assert_up_to_date(db._engine)

__all__ = ["app"]
