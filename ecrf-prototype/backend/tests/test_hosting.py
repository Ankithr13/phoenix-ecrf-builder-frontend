"""The Vercel and Supabase deployment: database URLs, and what gets uploaded."""

import json
from pathlib import Path

from ecrf.config import database_url

PROTOTYPE = Path(__file__).resolve().parents[2]


def test_postgres_urls_name_the_installed_driver():
    assert database_url("postgresql://u:p@host:6543/postgres") == "postgresql+psycopg://u:p@host:6543/postgres"
    assert database_url("postgres://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
    assert database_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
    assert database_url("sqlite:////tmp/x.db") == "sqlite:////tmp/x.db"


def test_vercel_sends_the_api_to_fastapi_and_never_uploads_keys():
    cfg = json.loads((PROTOTYPE / "vercel.json").read_text())
    assert cfg["rewrites"][0] == {"source": "/api/(.*)", "destination": "/api/index"}
    assert (PROTOTYPE / "api" / "index.py").exists()
    ignored = (PROTOTYPE / ".vercelignore").read_text().splitlines()
    for pattern in (".env", ".env.*", "**/.env", "backend/*.db", "backend/data/uploads"):
        assert pattern in ignored, pattern


def test_vercel_requirements_cover_the_backend():
    """requirements.txt is what Vercel installs; pyproject is what run.sh installs."""
    def names(lines):
        return {line.split(">=")[0].split("[")[0].strip().strip('"').lower()
                for line in lines if ">=" in line and not line.lstrip().startswith("#")}

    pyproject = (PROTOTYPE / "backend" / "pyproject.toml").read_text()
    runtime = pyproject.split("dependencies = [", 1)[1].split("\n]", 1)[0].splitlines()
    wanted = names(runtime) - {"uvicorn"} | {"psycopg"}
    assert names((PROTOTYPE / "requirements.txt").read_text().splitlines()) == wanted
