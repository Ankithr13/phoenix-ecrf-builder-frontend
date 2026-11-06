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

To see a run's cost, also set `LLM_PRICE_INPUT_PER_M`, `LLM_PRICE_CACHED_PER_M` and
`LLM_PRICE_OUTPUT_PER_M`. Without them the cost shows "not configured" rather than a
guess. An older `.env` using `PRICE_*` names needs renaming.

Other settings, all optional and commented in `.env.example`:

| Setting | Default | Does |
|---|---|---|
| `EXTRACT_STRATEGY` | `per_visit` | One model call per visit, or `per_form` |
| `QUOTE_MATCH_THRESHOLD` | `90` | How close a quote must be. A placeholder, not yet tuned |
| `SESSION_HOURS` | `12` | How long a login lasts |
| `DEMO_PASSWORD` | `demo1234` | Password for the demo accounts |
| `ECRF_ENV` | `dev` | `prod` turns off `/docs`, forces secure cookies and needs a private `SECRET_KEY` |
| `SEED_DEMO` | off | In `prod`, `1` creates the demo accounts |

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
| `admin@phoenix.demo` | Phoenix Clinical (sponsor) | admin |
| `builder@phoenix.demo` | Phoenix Clinical (sponsor) | database builder |
| `dm@phoenix.demo` | Phoenix Clinical (sponsor) | data manager |
| `cra@phoenix.demo` | Phoenix Clinical (sponsor) | monitor, Boston General only |
| `auditor@phoenix.demo` | Phoenix Clinical (sponsor) | read only |
| `pi@bgh.demo` | Boston General (site) | investigator |
| `crc@bgh.demo` | Boston General (site) | site coordinator |
| `entry@bgh.demo` | Boston General (site) | site data entry |
| `crc@mrc.demo` | Mercy Hospital (site) | site coordinator |

In development the login page lists these. A production build does not.
Who can do what is in `docs/roles-and-permissions.md`.

Sponsors upload protocols, review and lock forms, assign sites, approve
data and see statistics. Sites see only locked forms they are assigned
to, register patients, enter data and sign off visits. Either side can
raise queries.

## 6. Walk through

1. As `builder@phoenix.demo`: **Upload** a protocol (try
   `test_protocols/test_protocol6.pdf`, 31 pages) or click **Load sample**.
2. **Extract**: the model proposes the visit list, you confirm it, then
   one call per visit produces the fields. The cost and token count are
   shown on each run. Re-running the same protocol is free; answers are
   cached.
3. **Review**: every field quotes the protocol, and quotes that are not
   found were already deleted. Each protocol also gets a Foundation form and a
   visit date on every visit. Filter by status or source, edit a field, accept
   the library suggestions, approve the rest. **Edit checks** lists the checks.
4. As `dm@phoenix.demo`: **Review**, then **Lock form**. **Sites**: assign Boston General.
5. As `crc@bgh.demo`: open the study, register a patient, enter data. Values save
   as you go. A value out of range saves with a note and raises a query on submit;
   only a wrong format is refused. BMI, age and similar are computed from the
   inputs. **Submit visit** when done.
6. As `dm@phoenix.demo`: **Queries** has tabs by status and filters by site, visit,
   who raised it and check. Close what the checks raised. **Data review**: approve
   the values.
7. As `pi@bgh.demo`: **Notifications** says what is ready. Open the patient's visit
   and use **Sign off this visit**, which asks for your password again.
8. As `dm@phoenix.demo`: **Data review** lists whatever blocks **Lock study**.
   Once it is clear, lock the study. No data on it can change after that.

To see statistics, as `dm@phoenix.demo`:

1. **Dashboard**, **Results**, **Seed 20 synthetic subjects**, then approve the values on
   **Data review**.
2. **Analysis plan**: add a row, such as Systolic Blood Pressure, Day 1 to Week 12.
3. **Dashboard** has three tabs. **Queries 360** shows where queries stand, by week and
   site. **Page status** shows how far each subject has got, per site. **Results**
   shows each number next to an independent recalculation.

Also there: **Data listing** shows one form's values across subjects, with CSV export.
**Blank eCRF PDF** is on the Dashboard, and each subject has a **Casebook** PDF.
To require monitor review, as `admin@phoenix.demo` open **Admin**, **Approval chain**,
then as `cra@phoenix.demo` use **Data review** to mark visits reviewed.

Site staff have a short guide in `docs/ecrf-completion-guidelines.md`.

## 7. Tests

```bash
./run.sh test          # backend, 280 tests, 1 skipped, uses a temporary database
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
    verification/      independent statistics; imports nothing from ecrf/
    ecrf.db            SQLite database, created on first run
  frontend/            React + TypeScript + Vite
docs/                  roles, edit checks, analysis plan, database schema, sprint report
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
- **Postgres**: not supported yet. The independent statistics read SQLite only, so
  the dashboard's Results would fail, and hosting work was deferred before this was
  tested.
- **The backend refuses to start after pulling new code** on a database copied from
  somewhere else: it is behind the migrations. `./run.sh` migrates `backend/ecrf.db`,
  including moving old roles to the eight current ones. Back it up first if it matters.
