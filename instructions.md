# Running the eCRF prototype on a new machine

Protocol PDF in, draft electronic case report forms out, then a locked
form that sites enter data into. Everything below runs locally on macOS
or Linux. Windows works under WSL.

## 1. Prerequisites

| Need | Version | Check |
|---|---|---|
| Python | 3.11 or newer | `python3 --version` |
| Node.js | 18 or newer | `node --version` |
| Git | any | `git --version` |
| Poppler (optional) | any | `pdffonts -v` |

Poppler is only used to detect scanned PDFs quickly. Without it the code
falls back to a slower check; nothing breaks.

- macOS: `brew install python node poppler`
- Ubuntu / Debian: `sudo apt install python3 python3-venv nodejs npm poppler-utils`

## 2. Get the code

```bash
git clone https://github.com/jigark712/phoenix-ecrf-builder.git
cd phoenix-ecrf-builder/ecrf-prototype
```

## 3. Configure

```bash
cp .env.example .env
```

`.env` works as copied: it uses the **mock** extractor, which replays a
recorded run on the bundled sample protocol and needs no API key. That is
enough to see every screen.

To extract real protocols, open `.env` and set:

```
ECRF_BACKEND=openai_compat
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-6-luna
LLM_API_KEY=sk-...          # your key, never commit this file
```

`.env` is git-ignored. Any OpenAI-compatible endpoint works (Groq, Gemini,
a local vLLM); the commented blocks in `.env.example` show the settings.

## 4. Run

```bash
./run.sh
```

The first run takes a few minutes: it creates a Python virtual
environment, installs the backend, runs the database migrations, seeds
the demo accounts, installs the frontend packages and starts both servers.
Later runs take a few seconds.

- App: http://localhost:5173
- API explorer: http://localhost:8000/docs

Stop with `Ctrl-C`. `./run.sh backend` starts only the API.

## 5. Sign in

All demo accounts use the password `demo1234`.

| Account | Organisation | Role |
|---|---|---|
| `dana@phoenix.demo` | Phoenix Clinical (sponsor) | sponsor |
| `alex@phoenix.demo` | Phoenix Clinical (sponsor) | sponsor |
| `staff@bgh.demo` | Boston General (site) | site staff |
| `staff@mrc.demo` | Mercy Hospital (site) | site staff |

Sponsors upload protocols, review and lock forms, assign sites, approve
data and see statistics. Sites see only locked forms they are assigned
to, register patients and enter data. Either side can raise queries.

## 6. Walk through

1. As `dana@phoenix.demo`: **Upload** a protocol (try
   `test_protocols/test_protocol6.pdf`, 31 pages) or click **Load sample**.
2. **Extract**: the model proposes the visit list, you confirm it, then
   one call per visit produces the fields. The cost and token count are
   shown on each run. Re-running the same protocol is free; answers are
   cached.
3. **Review**: every field quotes the protocol, and quotes that are not
   found were already deleted. Filter by status or source, edit a field,
   accept the library suggestions, approve the rest. Lock when nothing is
   left undecided.
4. **Sites**: assign Boston General.
5. As `staff@bgh.demo`: open the study, register a patient, enter data.
   Out-of-range values are refused; BMI, eGFR and similar are computed
   from the inputs.
6. As `dana@phoenix.demo`: **Data review** shows the entered values.
   Raise a query, approve a value. **Dashboard** counts approved values
   only, next to an independent recomputation.

## 7. Tests

```bash
./run.sh test          # backend, 143 tests, uses a temporary database
cd frontend && npm run build && npm run lint
```

## 8. Where things are

```
ecrf-prototype/
  run.sh               one command for everything
  .env.example         every setting, with comments
  backend/
    ecrf/              the application (see CLAUDE.md at the repo root for the map)
    migrations/        Alembic; run.sh applies them
    tests/             pytest
    scripts/           seed_demo.py, fetch_ctgov_protocol.py
    ecrf.db            SQLite database, created on first run
  frontend/            React + TypeScript + Vite
test_protocols/        public protocols from ClinicalTrials.gov, with a README of results
```

## 9. If something goes wrong

- **"attempt to write a readonly database"** after running tests with the
  server up: restart `./run.sh`. (Current tests use a temporary database,
  so this should no longer happen.)
- **502 "extraction failed"**: the model call failed. Check the key in
  `.env`, then the model name against the provider's model list.
- **413 or rate-limit errors** on a free tier: the whole protocol goes in
  one request on the first call, so free tiers with small per-minute
  limits cannot process long protocols. Use a paid key or a short
  protocol (`test_protocol2.pdf`, 6 pages).
- **Port in use**: stop whatever is on 8000 or 5173, or edit the ports in
  `run.sh` and `frontend/vite.config.ts`.
- **Postgres instead of SQLite**: set `DATABASE_URL=postgresql+psycopg://...`
  in `.env`; the migrations run the same way.
