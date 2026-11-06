#!/bin/zsh
# Demo mode, on the usual address, http://localhost:5173
#
#   ./demo.sh start   A fresh demo database. Run it again before every retake.
#   ./demo.sh stop    Back to the normal database.
#
# The demo database holds the nine demo accounts and the bundled sample protocol
# with its form locked, Boston General and Mercy assigned, and 20 synthetic subjects
# whose values wait for approval. It is built with the mock extractor, so building
# it costs nothing. When the code's migrations move on, it is rebuilt from nothing,
# and the old files are kept in db/stale-<date>.
#
# The server itself follows your .env. If that names a paid model, extracting an
# uploaded PDF here is a live, paid call. ECRF_BACKEND=mock ./demo.sh start avoids it.

HERE=${0:A:h}
APP="$HERE/../../ecrf-prototype"
PORT=${DEMO_PORT:-8000}
DB=${DEMO_DB_DIR:-$HERE/db}
PY="$APP/backend/.venv/bin/python"
BUILD="$APP/backend/scripts/build_demo_db.py"

stop_backend() {
  local pids=$(lsof -ti tcp:$PORT -sTCP:LISTEN)
  [[ -n "$pids" ]] && kill ${=pids}
  while lsof -ti tcp:$PORT -sTCP:LISTEN >/dev/null; do sleep 0.2; done
}

wait_for_backend() {
  for i in {1..60}; do
    curl -sf localhost:$PORT/api/health >/dev/null && return 0
    sleep 0.25
  done
  echo "The backend did not start. See $1"; exit 1
}

frontend_running() { lsof -ti tcp:5173 -sTCP:LISTEN >/dev/null }

start_frontend() {
  frontend_running && return 0
  (cd "$APP/frontend" && nohup npm run dev -- --port 5173 > "$DB/frontend.log" 2>&1 &)
  for i in {1..60}; do frontend_running && return 0; sleep 0.25; done
  echo "The frontend did not start. See $DB/frontend.log"; exit 1
}

# clean.db is what each retake starts from. Rebuild it only when the schema is behind.
ensure_clean() {
  "$PY" "$BUILD" --current "$DB/clean.db" && return 0
  local keep="$DB/stale-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$keep"
  [[ -f "$DB/clean.db" ]] && mv "$DB/clean.db" "$keep/"
  [[ -f "$DB/demo.db" ]] && mv "$DB/demo.db" "$keep/"
  echo "The demo database was behind the code, so it is being rebuilt. Old files: $keep"
  (cd "$APP/backend" && DATABASE_URL="sqlite:///$DB/clean.db" ECRF_UPLOAD_DIR="$DB/uploads" "$PY" "$BUILD") \
    || { echo "Building the demo database failed."; exit 1; }
}

case "$1" in
  start)
    stop_backend
    mkdir -p "$DB"
    rm -rf "$DB/uploads"; mkdir -p "$DB/uploads"
    ensure_clean
    cp "$DB/clean.db" "$DB/demo.db"
    (cd "$APP/backend" && DATABASE_URL="sqlite:///$DB/demo.db" ECRF_UPLOAD_DIR="$DB/uploads" \
      nohup .venv/bin/uvicorn ecrf.api.app:app --port $PORT > "$DB/backend.log" 2>&1 &)
    wait_for_backend "$DB/backend.log"
    start_frontend
    echo "Demo ready. Open http://localhost:5173. The login page lists the nine accounts."
    ;;
  stop)
    stop_backend
    (cd "$APP/backend" && nohup .venv/bin/uvicorn ecrf.api.app:app --port $PORT > "$DB/backend-normal.log" 2>&1 &)
    wait_for_backend "$DB/backend-normal.log"
    start_frontend
    echo "Back to the normal database on http://localhost:5173"
    ;;
  *)
    echo "usage: ./demo.sh start | stop"; exit 1
    ;;
esac
