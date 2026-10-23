#!/usr/bin/env bash
# One command to run the whole prototype.
#   ./run.sh            backend + frontend, mock backend
#   ./run.sh backend    backend only
#   ./run.sh test       backend tests, against a temporary database
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || cp .env.example .env

# ---------- backend ----------
cd backend
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e ".[dev]"
[ -f data/sample/PHX-401-201_protocol.pdf ] || python data/sample/make_sample_protocol.py

if [ "${1:-}" = "test" ]; then
  # tests/conftest.py points DATABASE_URL at a temporary file, so the dev
  # database is never touched. An earlier version deleted ecrf.db here and
  # a running server then kept writing to the deleted inode.
  python -m pytest -q
  exit 0
fi

# The schema is owned by Alembic. The server refuses to start if this has
# not been run, so it runs every time.
alembic upgrade head

uvicorn ecrf.api.app:app --port 8000 --reload &
BACK=$!
cd ..

if [ "${1:-}" = "backend" ]; then
  wait $BACK
  exit 0
fi

# ---------- frontend ----------
cd frontend
[ -d node_modules ] || npm install --silent
npm run dev -- --port 5173 &
FRONT=$!
cd ..

echo
echo "  backend   http://localhost:8000/docs"
echo "  frontend  http://localhost:5173"
echo
trap "kill $BACK $FRONT 2>/dev/null" EXIT
wait
