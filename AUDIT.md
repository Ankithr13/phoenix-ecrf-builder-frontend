# AUDIT.md

Read-only audit, 2026-10-22. Describes the code **as it runs today**, not as
`BUILD.md` specifies it. Nothing in the repo was modified; the database was
copied to `/tmp` and read from the copy. No LLM API was called.

## 0. Snapshot

| Item | Value |
|---|---|
| Root / branch | `/Users/Asus/Documents/BU Spark ECRF` / `spark-test` |
| Remote `origin` | `https://github.com/Priyanshusingh09876/Spark-test.git` |
| Remote `spark` | `https://github.com/BU-Spark/se-phoenix-clinical.git` |
| Uncommitted | none before this file was written |
| Python (system + `.venv`) | 3.14.3 (`requires-python >=3.11`, CI uses 3.12) |
| Node / npm | v25.6.1 / 11.9.0 |

Commits (6 in total, not 10; `spark-test` is an orphan branch sharing no
history with that repo's `main`):

`24a550a` 10-16 Rewrite the CI README around the project · `5a753b6` 10-16 Add
a CI README · `945bce5` 10-16 Remove test_protocol4.pdf, committed by accident
· `83acb17` 10-16 Run the CI pipeline on this branch · `a2c5b31` 10-16 Fix
dashboard 500 when a statistic cannot be computed · `56381e0` 10-15 Initial
commit of spark-test code

**pytest: 3 passed, 0 failed** (run with `DATABASE_URL` pointed at `/tmp` so
the dev database survived; `run.sh test` would have deleted it). Two
`DeprecationWarning`s for `@app.on_event("startup")` (`ecrf/api/app.py:24`).

**Health check in mock mode: worked**, on port 8099 against a throwaway
database, then stopped:
`{"ok":true,"version":"0.1.0","backend":"mock","model":"recorded","context_mode":"auto","quote_match_threshold":90}`

A dev server was already running on :8000 (`openai_compat`, `gpt-5.1`) with
Vite on :5173. Neither was touched.

## 1. Tree

```
.github/workflows/ecrf-ci.yml   NEW  lint -> test -> build
BUILD.md  README.md                  spec (3635 lines), setup
CLAUDE.md                       NEW  invariants + traps for agents
CI_README.md                    NEW  CI write-up for coursework
docs/pipeline.png               NEW  README diagram
test_protocols/                 NEW  1,2,3 tracked; 4 ignored (15 MB)
ecrf-prototype/
  run.sh  .env(ignored)  .env.example
  backend/
    pyproject.toml                   deps + pinned ruff rules
    ecrf.db                     NEW  dev SQLite, 2.7 MB, ignored
    data/ cdash_library.yaml         rebuilt from client docx
          recorded/PHX-401-201.json  fixture the mock replays
          sample/                    synthetic 4-page protocol
          protocols/            NEW  11 ClinicalTrials.gov PDFs (ignored)
          uploads/              NEW  9 uploaded PDFs (ignored)
    ecrf/ config schema ingest sections verify cdash pipeline
          extract/{base=adapter, mock, openai_compat, prompts}
          stats/{calculations, registry, seed}
          storage/{db, models}   api/{app, protocols, data, dashboard}
    scripts/fetch_ctgov_protocol.py  downloads real protocols
    tests/test_pipeline.py           3 tests, mock backend
    verification/expected_results.py independent stats, raw sqlite3
  frontend/
    eslint.config.js            NEW  flat config, added for CI
    public/logo.png             REPLACES BUILD.md's public/logo.svg (REMOVED)
    src/ api/{client,types}  components/{Layout,Badge,FieldCard,Stat,charts}
         pages/{Protocols,Review,DataEntry,Dashboard}  styles/
```

## 2. Deviations from BUILD.md

Produced mechanically: all 44 file bodies extracted from BUILD.md and diffed
against the tree. Cosmetic diffs (import order, `noqa`, `raise ... from e`,
`datetime.UTC`) omitted.

| Area | BUILD.md said | Code does now | File |
|---|---|---|---|
| Quote scoring | verbatim hit short-circuits to hardcoded `100.0` | score measured for every quote; `verdict` = how it matched, `score` = how well | `ecrf/verify.py:29-54` |
| Threshold | applied only when verdict is `approximate` | applied to every field, verbatim included | `ecrf/verify.py:82-83` |
| Section bodies | rebuilt with `""` bodies | sliced out of stored text | `ecrf/api/protocols.py:44-46` |
| Dashboard JSON | raw floats | NaN/inf -> `null` in the response only; compare still on raw values | `ecrf/api/dashboard.py:27-41,89-95` |
| Unsupported-analysis panel | dashboard row 4, input + Request button | removed from UI; endpoint still 403s | `pages/Dashboard.tsx:39-44`, `api/dashboard.py:105-116` |
| Section cross-check | shown per field | computed, deliberately not rendered | `components/FieldCard.tsx:62` |
| CDASH library | seed from general knowledge, `VSORRES_SYSBP` codes | rebuilt from client document, CDASH variables (`SYSBP`), 5 domains / 62 fields | `data/cdash_library.yaml`, `tests/test_pipeline.py:44` |
| Ruff / ESLint | unspecified | explicit rule set, `B008`+`E501` ignored with reasons; flat ESLint config added | `pyproject.toml:38-58`, `eslint.config.js` |
| Groq model | `llama-3.3-70b-versatile` | retired by provider; example now `openai/gpt-oss-120b` | `.env.example` |
| Logo | `logo.svg` placeholder | `logo.png`, real client logo | `components/Layout.tsx:26` |

BUILD.md never specified login, roles, locking, queries or deployment; `X-User`
was always labelled a stand-in (`BUILD.md:1547`).

## 3. Extraction as it actually runs

`.env`: `ECRF_BACKEND=openai_compat`, `LLM_BASE_URL` host `api.openai.com`,
`LLM_MODEL=gpt-5.1`, `LLM_TEMPERATURE=0`, `ECRF_CONTEXT=auto`,
`ECRF_CONTEXT_TOKEN_LIMIT=60000`, `QUOTE_MATCH_THRESHOLD=90`, `LLM_API_KEY` set
(not printed). `DATABASE_URL` unset, so `sqlite:///backend/ecrf.db`
(`config.py:57`).

**Context mode actually used: `full`, for every stored run.** `auto` only
switches above 60,000 tokens (`pipeline.py:20-29`); the largest protocol is
37,010. Section selection works (`sections.py:43-62`, 12,000-token budget) but
has never fired at this limit, and **pass one always sends the whole protocol**
whatever the mode (`pipeline.py:41`).

```
POST /api/protocols/{id}/extract      api/protocols.py:122
  pipeline.run                        pipeline.py:32
    1 call  list_visits(doc.text)     pipeline.py:41     whole protocol
    N calls fields_for_visit(ctx,v,visits) pipeline.py:48-50  one per visit
            -> verify.filter_fields / cdash.enrich  pipeline.py:51-52
  db.save_version                     api/protocols.py:136
```

**Calls = visits + 1**, strictly sequential so the first call writes the
provider's prompt cache (`pipeline.py:6-8`). No concurrency.

Prompt order (`extract/prompts.py:47-72`): 1 system `SYSTEM` block, stable ·
2 user `PROTOCOL:\n\n{text}`, stable in `full` mode, per-visit in `sections`
mode · 3 `STUDY VISITS: ...` (pass two), stable within a run · 4 `TASK: ...
"{visit}" visit only` + JSON schema, varies.

**Prefix caching: yes in `full` mode.** System + protocol is byte-identical
across calls and nothing variable precedes it (no timestamp, request id or
visit name). In `sections` mode every pass-two call is a miss.

**Result cache keyed by protocol hash: MISSING.** `text_hash` is stored
(`models.py:29`) and pinned per version (`db.py:57`) but never read as a key;
the only content lookup is `filename` for the bundled sample
(`protocols.py:104`). The same PDF re-extracts in full: ids 7, 8, 9 all hold
hash `d058b8c0e2`, and 8 and 9 were each extracted from scratch.

Response format `{"type":"json_object"}`, retried once without it if the
provider rejects it (`openai_compat.py:41-46`). **One retry**, only for invalid
JSON or Pydantic failure (`openai_compat.py:49-63`); none for 429 or 5xx.
**`max_tokens` is never set**, which is why a 5,500-token prompt was billed as
8,228 against a per-minute limit.

**Token and cost logging: MISSING.** `resp.usage` is never read
(`openai_compat.py:38-47`); the API passes `log=lambda *_: None`
(`protocols.py:133`), discarding even progress lines. Only `seconds` persists.

Every past run (13 version rows). In/out tokens **estimated** (protocol tokens
x calls; stored JSON / 4) because usage was never recorded.

| Prot | Pages | v | Visits | Calls | In~ | Cached | Out~ | Secs | Kept | Flag | Rej | Model |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4 | 1 | 5 | 6 | — | — | — | 0.04 | 44 | 1 | 1 | mock |
| 1 | 4 | 3 | 5 | 6 | 11,244 | UNKNOWN | UNKNOWN | 47.8 | 54 | 0 | 0 | gpt-4.1 |
| 1 | 4 | 4 | 5 | 6 | 11,244 | UNKNOWN | 10,133 | 85.6 | 71 | 8 | 0 | gpt-5.1 |
| 2 | 11 | 1 | 8 | 9 | 51,687 | UNKNOWN | 4,340 | 321.3 | 32 | 4 | 0 | gpt-oss-120b |
| 3 | 6 | 1 | 4 | 5 | 14,755 | UNKNOWN | 4,305 | 186.1 | 38 | 24 | 0 | gpt-oss-120b |
| 5 | 6 | 1 | 4 | 5 | 14,755 | UNKNOWN | 5,462 | 134.1 | 38 | 19 | 6 | gpt-oss-120b |
| 6 | 76 | 2 | 8 | 9 | 328,230 | UNKNOWN | 51,235 | 554.1 | 325 | 172 | 14 | gpt-5.1 |
| 8 | 75 | 3 | 18 | 19 | 714,590 | UNKNOWN | 75,387 | 744.7 | 446 | 226 | 46 | gpt-5.1 |
| 9 | 75 | 1 | 8 | 9 | 338,490 | UNKNOWN | 32,572 | 369.6 | 196 | 123 | 16 | gpt-5.1 |

Protocols 4 and 7 were uploaded, never extracted. **Cost per run: UNKNOWN**
until `usage` is persisted. Protocols 8 and 9 are the same PDF: 18 visits
against 8, 446 fields against 196.

## 4. Verification (quote matching)

| Element | Where | Detail |
|---|---|---|
| Threshold 90 | `config.py:56`, `.env` | documented as a placeholder, never tuned |
| Match normalisation | `verify.py:25-26` | collapse whitespace, strip, lowercase |
| Document normalisation | `ingest.py:76-86` | quotes/dashes to ASCII, rejoin hyphen breaks; called once, from `load()` |
| Matcher / verdict | `verify.py:46-54` | `rapidfuzz.partial_ratio_alignment`; substring -> `exact`, else `approximate` |
| Cutoff | `verify.py:82-83` | `score < threshold` -> `rejected`, any verdict |
| Section check | `verify.py:57-74` | proportional offset map, parent fallback, `None` if unknown |
| Display rounding | `verify.py:85` | `round(score,1)` **after** the cutoff |

Kept fields by score bin (latest version per protocol):

| Prot | 100 | 95-99 | 90-94 | 80-89 | <80 | Kept | Distinct quotes |
|---|---|---|---|---|---|---|---|
| 1 | 71 | 0 | 0 | 0 | 0 | 71 | 15 |
| 2 | 28 | 4 | 0 | 0 | 0 | 32 | 11 |
| 3 | 36 | 2 | 0 | 0 | 0 | 38 | 19 |
| 5 | 37 | 0 | 1 | 0 | 0 | 38 | 10 |
| 6 | 261 | 44 | 20 | 0 | 0 | 325 | 129 |
| 8 | 377 | 45 | 24 | 0 | 0 | 446 | 167 |
| 9 | 174 | 12 | 10 | 0 | 0 | 196 | 92 |

82 rejections across all versions, scores 65.5 to 90.0. **One reads `90.0`**:
the cutoff uses the raw score and rounding happens afterwards, so 89.95 is
rejected and displayed as `90.0%` against a threshold of 90.

Three approximate matches, model quote vs protocol text (trimmed):

1. Systolic BP, prot 2, 99.4 — `The key visits are Visit 13 (Re‑randomization)
   and Visit 15 (Week 40) as BP measurements collected during these two visits
   are needed to derive the study key secondary endpoint.` vs identical text
   with a plain hyphen in `Re-randomization`.
2. Diastolic BP, prot 2, 99.0 — `need to be measured at on‑site visits (i.e.,
   at Visits 4, 6, 11 and 13) with an unattended AOBPM device` vs identical
   with `on-site`.
3. Systolic BP, prot 2, 99.4 — the same sentence as #1, cited by a second field.

All three differ only by a non-ASCII hyphen that `normalise()` had already
converted. This is the fuzzy tier earning its place.

Three rejections:

1. `Right heart catheterization performed`, prot 5, 89.4 — quote `[Section 3]
   Right heart catheterization performed at Screening with results that are:`
   vs text `1 PAH. 3. Right heart catheterization performed at Screening with
   results that are: a`.
2. `Right heart catheterization results`, prot 5, 89.4 — same quote, same text.
3. `Persistent hypotension`, prot 5, 89.6 — quote `[Section 2] Persistent
   hypotension at Screening.` vs text `tension 2. Persistent hypotension at
   Screening.`

**All 6 of protocol 5's rejections start with `[Section N]`**, a prefix added
by section selection when assembling context (`sections.py:60`) and copied into
the quote by the model. It does not exist in the protocol, so the score fell
just under 90. Good fields killed by context formatting, not fabrications. It
also shows at least one stored run used `sections` mode although `.env` now
reads `auto`.

**Labelled data: PARTIAL and weak.** Reviewer decisions live only as `status`
inside versions, so diffing versions is the sole label source. That yields **2
field-level human judgements** in the whole database (protocol 1 and protocol
8, each one field flagged -> approved with a range edit) plus two bulk
`approve_all_remaining` actions covering 153 and 219 fields. No field has ever
been set `rejected` by a human. Nothing here can measure precision or recall.

## 5. Flagged fields

| Prot | none | missing | conflicting | ambiguous | unsupported | Flagged % |
|---|---|---|---|---|---|---|
| 1 | 63 | 8 | 0 | 0 | 0 | 11% |
| 2 | 28 | 3 | 0 | 1 | 0 | 13% |
| 3 | 14 | 11 | 0 | 0 | 13 | 63% |
| 5 | 19 | 19 | 0 | 0 | 0 | 50% |
| 6 | 153 | 159 | 0 | 6 | 7 | 53% |
| 8 | 220 | 188 | 0 | 38 | 0 | 51% |
| 9 | 73 | 118 | 1 | 4 | 0 | 63% |

`missing` dominates; on real protocols about half of all kept fields are
flagged and nothing groups or ranks them. Five examples (protocol 1):

- **Sex** / missing — "Protocol requires recording sex but does not specify
  allowed response options; choices list left null."
- **Adverse Event Term** / missing — "The protocol does not specify whether
  multiple adverse events can be recorded per subject at a visit; repeats is
  set to 1 at field level but the AE form will typically be a repeating log."
- **AE Start Date** / missing — identical note, repeated verbatim.
- **AE Severity** / missing — identical note, repeated verbatim.
- **ECG Performed** / missing — "Week 4 is not listed as a visit where ECG is
  performed, so ECG-related fields are not collected at Week 4; this field is
  included only to reflect the protocol statement about recording whether ECG
  was performed at visits"

Driven by `extract/prompts.py:31-36`: rule 3 "Never state a value the protocol
does not give ... leave it null", rule 4 "If the protocol is unclear,
contradictory, or silent on something it should specify, keep the field but set
issue to one of: missing, conflicting, ambiguous, unsupported ... Flagging
beats guessing." Rule 3 forces the null and rule 4 then demands a flag for the
same silence, so a protocol that omits units yields one flag per field by
design. Status follows the issue at `verify.py:89-90`.

## 6. CDASH and field library

`data/cdash_library.yaml`: 5 domains, 62 fields. DM Demographics (ENRL-002) 5:
Date of Birth, Sex, Race, Ethnicity, Country of Residence · VS Vital Signs
(SAFE-006) 12 incl. Weight, Height, **Body Mass Index** (`BMI`, kg/m2, 10-80) ·
EG ECG (SAFE-007) 10 · LB Laboratory (SAFE-008) 18 · AE Adverse Events
(SAFE-003) 17.

| R2 element | In library | Note |
|---|---|---|
| Informed consent (DS/IE/IC) | **MISSING** | header lists MH, CM, IE, DS, EX/DA, DV, PR, HO, CE, SD as not carried over |
| Demographics incl. race | DONE | DM |
| Height, Weight | DONE | VS |
| BMI | PARTIAL | an ordinary decimal field; nothing derives it |

Matching (`cdash.py:39-47`): exact lookup on lowercased name or alias, then
`rapidfuzz.process.extractOne` with `token_set_ratio`, cutoff **85**. `enrich`
attaches `cdash` and `domain` and backfills only null `unit`, `min`, `max`,
`choices` (`cdash.py:50-65`). **It never adds a field.** Library fields the
model did not produce return separately from `suggestions()` (`cdash.py:68-81`)
into a collapsed panel (`pages/Review.tsx:187-200`).

**Fixed foundation form: MISSING.** Every field originates from the model.
Consent appears only when the protocol states it: present in protocols 1, 6, 8,
9; absent in 2, 3, 5. Race and ethnicity appear in **no** stored draft. BMI
appears once (protocol 6).

**Derived / calculated fields: MISSING.** No `derived`, `calculated` or
`formula` concept in `ecrf/` or the library, and no expression evaluator. BMI
from height and weight needs a new field kind in `schema.py`, computation in
`api/data.py` and a read-only widget.

Types (`schema.py:11`): `integer, decimal, text, date, choice, boolean`,
rendered as number / text / date / select / checkbox
(`pages/DataEntry.tsx:195-223`). No file upload, time, multi-select or textarea.

## 7. Data model

SQLite selected by `DATABASE_URL` with a file default (`config.py:57`);
`check_same_thread` passed only for sqlite (`db.py:9-13`). **No migration
tool**: tables come from `create_all` at startup (`db.py:16-17`,
`app.py:24-26`). `psycopg` is already an optional extra (`pyproject.toml:22`).

| Table (rows) | Columns | Notes |
|---|---|---|
| `protocol` (9) | id PK · name, filename · text_hash str(64) · normalised text · sections JSON · pages, tokens_estimate int · uploaded_by, uploaded_at | filename not unique, so the same PDF stores repeatedly; `sections` is `[{number,title,page,start,end}]`; `text_hash` never used as a cache key |
| `ecrf_version` (13) | id PK · protocol_id FK · protocol_hash · version int · content JSON · created_by, created_at, note | `UniqueConstraint(protocol_id, version)`; `content` is **the whole DraftECRF**, 17 KB to 301 KB |
| `observation` (2,215) | id PK · protocol_id FK · subject_id, visit, field_name str · repeat_num int · value_num float / value_text str · synthetic bool · entered_by, entered_at | unique on the first five; `field_name` is a **string with no FK** to any field definition; `entered_by` seen: `seed`, `demo-reviewer` |

Only the two implicit unique indexes exist; nothing indexes `protocol_id`,
`subject_id` or `visit`. eCRF content is **one JSON blob per version**
(`models.py:55`), not normalised rows.

Postgres breakage: `verification/expected_results.py:16-20` uses `sqlite3`
directly and raises on any non-sqlite URL, and the dashboard imports it
(`api/dashboard.py:20-21`), so the comparison column dies · default DB is a
file beside the code (`config.py:57`) · uploads land on local disk
(`protocols.py:20,75-77`) · 301 KB JSON blobs rewritten per version · no
migrations.

## 8. Versioning, locking, audit

New versions are inserted, never updated (`db.py:51-65`), in two places:
extraction, `note="initial extraction"` (`protocols.py:136`), and review,
`note="review: N change(s)"` (`protocols.py:232`).

**Per change, only the new state is stored.** Old vs new is recoverable solely
by diffing two versions, which is how section 4's numbers were produced. No
change log, no per-field author or timestamp, and **no reason**:
`FieldChange.reviewer_note` is declared (`protocols.py:193`) and never read,
the apply loop copying only `status, min, max, required, repeats`
(`protocols.py:218-221`). One free-text note covers a whole version.

**Lock or frozen state: MISSING.** `Status` has no `locked` member
(`schema.py:13`), and `review` reads `latest_version` and writes another
version with no check on its state (`protocols.py:202-234`), so **an approved
version can still be changed through the API**. Re-running extraction on a
reviewed protocol writes a fresh version with every status back to `draft`;
the database contains exactly that event, protocol 1 v2 -> v3, noted "initial
extraction", reverting the one field a reviewer had approved and re-ranged.

**Data entry edits overwrite.** `enter` upserts on `(protocol, subject, visit,
field, repeat)` and replaces the value in place (`api/data.py:95-100`). The
previous value is gone and `entered_at` is not even refreshed.

## 9. Users and access

No user model, no login, no sessions, no tokens. Identity arrives as an
`X-User` header defaulted to `demo-user` (`protocols.py:24-28`) and hardcoded
to `demo-reviewer` in the browser (`api/client.ts:9`). It is used only to fill
`uploaded_by`, `created_by` and `entered_by`. **No endpoint inspects it to
decide anything.** No roles, no site concept, no patient ownership:
`subject_id` is free text typed in the browser, default `PHX-021`
(`pages/DataEntry.tsx:43`). Any caller can approve a form, enter data for any
subject and read every protocol. The two values in `uploaded_by` reflect the
test client and the browser sending different headers, not authentication.

## 10. API

Auth column: "header" means `X-User` is recorded, never checked.

| Method | Path | Purpose | Key request | Key response | Auth |
|---|---|---|---|---|---|
| GET | `/api/health` | liveness + config echo | — | ok, version, backend, model, context_mode, threshold | none |
| GET | `/api/protocols` | list + latest summary | — | id, name, pages, tokens_estimate, latest_version, summary | none |
| POST | `/api/protocols/upload` | upload, ingest, store text+sections | multipart `file` | id, pages, tokens_estimate, sections, tables | header |
| POST | `/api/protocols/sample` | load bundled sample | — | id, name, already_loaded | header |
| POST | `/api/protocols/{id}/extract` | run pipeline, write version | `backend` query override | version, summary | header |
| GET | `/api/protocols/{id}/draft` | latest version + suggestions | — | protocol, version, draft, library_suggestions | none |
| GET | `/api/protocols/{id}/versions` | version history | — | version, created_by, created_at, note, summary | none |
| GET | `/api/protocols/{id}/section/{n}` | read a cited section | — | number, title, page, text | none |
| POST | `/api/protocols/{id}/review` | apply edits, new version | `changes[]`, `note`, `action` | version, applied | header |
| POST | `/api/data/validate` | validate only | protocol_id, subject_id, visit, readings | ok, errors | none |
| POST | `/api/data/enter` | validate then upsert | same | saved | header |
| POST | `/api/data/seed/{id}` | 20 synthetic subjects | — | seeded, already | none |
| GET | `/api/data/{id}/subjects` | subjects and visits | — | subject_id, visits | none |
| GET | `/api/dashboard/calculations` | approved registry | — | name, label, unit, kind | none |
| GET | `/api/dashboard/{id}` | summary, counts, stats | — | protocol, extraction, data, stats | none |
| POST | `/api/dashboard/{id}/unsupported` | demonstrates refusal | `name` query | always 403 | none |

## 11. Frontend

React 18 + TypeScript + Vite, plain CSS, hand-rolled SVG charts, no UI kit.
Routes (`App.tsx:11-18`): `/` Protocols, `/review/:id`, `/data/:id`,
`/dashboard/:id`, catch-all redirect. Protocols: load sample, upload, extract,
links. Review: visit tabs, a `FieldCard` per field with quote, verdict and
score, section viewer panel, range and required edits, Approve / Flag / Reject,
"Approve all remaining", review note, version history. DataEntry: visit select,
free-text subject id, one control per field per repeat, client validation
mirroring the server, seed button. Dashboard: stats, charts, comparison table.

State is local `useState` per page with a `load()` callback; no store, no query
cache. `api/client.ts` is the only file with URLs and sets `X-User` on every
request (`client.ts:9-22`). Types are mirrored by hand in `api/types.ts`.

Dashboard data: Subjects and Readings from `observation` counts · Fields kept
from the summary · verification donut (exact/approximate/rejected) · fields per
visit bar · subjects per visit bar · the app-vs-independent scalar table.
**Nothing is hardcoded or faked.** The caveat is upstream: every observation is
synthetic, 1,462 of 2,215 rows come from `stats/seed.py`, and the visit names
the calculations key on (`Day 1`, `Week 12`, `calculations.py:14-16`) match the
seeder, not real protocols, so on protocol 8 the mean-change figure is `null`
and renders "not available".

**Role-specific views: MISSING.** One navigation, every action visible to
anyone. Logo: real client logo at `public/logo.png` (`Layout.tsx:26`); all
colours and sizes are tokens in `styles/tokens.css`, diverged from BUILD.md by
32 lines during the visual pass; a header pill shows backend and model
(`Layout.tsx:45`).

## 12. Stats

Registered (`stats/registry.py:22-41`): `mean_change_systolic` (scalar, mmHg),
`subjects_per_visit` (by_visit), `percent_missing` (scalar, %).
`calculations.py:7-9` labels the set a placeholder the client has not
confirmed. `registry.run` raises `UnsupportedAnalysis` for anything else
(`registry.py:57-61`) and there is no free-text query path.

**Stats read all entered data; there is no concept of approved data.**
`load_frame` selects every observation for the protocol (`registry.py:49-54`),
and `observation` has no status, no reviewed flag and no link to a version. R4's
"only approved data goes to stats" has nothing to stand on.

**`verification/` still imports nothing from `ecrf/`**: only `sqlite3`, `sys`,
`collections`, `pathlib` (`expected_results.py:10-13`). The dashboard imports
it one way to compare (`dashboard.py:20-21`) and a test asserts every
statistic agrees (`tests/test_pipeline.py:58`).

## 13. Deployment readiness

No Dockerfile, compose file, Procfile or Railway config exists. CI
(`.github/workflows/ecrf-ci.yml`) runs lint (ruff + eslint), test (pytest with
JUnit XML and a step summary) and build (`tsc` then `vite`), with build gated
by `needs: [lint, test]`. It deploys nothing. The frontend calls relative
`/api`, resolved by the Vite dev proxy (`vite.config.ts:8`). CORS is hardcoded
to `localhost:5173` and `127.0.0.1:5173` (`app.py:13-17`); ports 8000 and 5173
are hardcoded in `run.sh:27,39` and `vite.config.ts:7`.

Breaks on Railway today: **`$PORT` ignored** (`--port 8000` fixed) ·
**SQLite on ephemeral disk**, wiped per redeploy · **the dashboard breaks on
Postgres** because the independent verification module is sqlite-only ·
**no migrations** · **uploaded PDFs vanish with the container** ·
**nothing serves the built frontend**, no static mount · **CORS rejects the
deployed origin**.

**Monorepo: still standalone.** The code sits on orphan branch `spark-test` of
`BU-Spark/se-phoenix-clinical`, sharing no history with that repo's `main`,
which holds a different project (including its own
`.github/workflows/ci.yml`, which is why ours is named `ecrf-ci.yml`). Folding
it in as a subdirectory is a move plus a workflow path change, not a rewrite.

## 14. Requirement map

| ID | Status | Exists now (file) | Missing | Size | Open question |
|---|---|---|---|---|---|
| R1 CDASH | PARTIAL | 62 fields across DM/VS/EG/LB/AE (`data/cdash_library.yaml`); deterministic enrichment (`cdash.py:50-65`) | 10 modules not carried over; no ODM / Define-XML export; no controlled-terminology validation | M | which CDASH IG version is contractual? |
| R2 Foundation fields | MISSING | consent only when the protocol states it (4 of 7 drafts); DM and VS exist in the library | fixed form prepended to every eCRF with consent first; race and ethnicity never generated; **no BMI derivation** anywhere | M | is the foundation set identical for every study? |
| R3 Client CRF library | PARTIAL | YAML transcribed against the client document (`cdash_library.yaml:1-25`) | the library itself not received; no importer; no library versioning | M-L | what format, and does it carry edit checks? |
| R4 Login and roles | MISSING | `X-User` recorded into audit columns (`protocols.py:24-28`) | authentication, user table, roles, per-endpoint checks, sites, patient ownership, approve-and-lock, approved-data gate for stats | L | which identity provider, and is 21 CFR Part 11 in scope? |
| R5 Review chain | MISSING | single-step review writing a new version (`protocols.py:202`) | reviewer sequence, per-reviewer state, transitions, notifications | M-L | how many reviewers, fixed order? |
| R6 Audit trail | PARTIAL | append-only `ecrf_version`, who and when per version | old vs new per change; reason (`reviewer_note` dropped, `protocols.py:193`); **data entry overwrites with no history** (`data.py:99-100`) | M | is a diffable version chain enough, or a per-field change log? |
| R7 Queries and alerts | MISSING | nothing; `issue`/`issue_note` are model output, not a conversation | query table, open/answered/closed states, alerts, comments, sticky notes, field metadata | L | who may raise and close a query, is there an SLA? |
| R8 Dashboard metrics | PARTIAL | every chart computed from stored data, each scalar independently recomputed (`dashboard.py:89-95`) | 3 placeholder metrics keyed to seeded visit names (`calculations.py:14-16`); no per-role views; no enrollment, query or completeness metrics | M | which metrics does the sponsor report? |
| R9 Cost and time | PARTIAL | visits+1 calls, sequential for prefix caching (`pipeline.py:6-8`); section selection implemented (`sections.py:43`) | **no result cache**, same PDF re-extracts (ids 7,8,9 share a hash); selection never fires at 60,000 and **never applies to pass one** (`pipeline.py:41`); no `max_tokens`; **no usage or cost logging**; ~50% of fields still flagged | M | is a hash-keyed cache acceptable after an amendment? |
| R10 Measure accuracy | MISSING | match scores per field; rejections stored with quote and score | no reference eCRF; only 2 field-level human judgements; no precision/recall harness; threshold never tuned (`config.py:39-41`) | M | what form does the reference eCRF take? |
| R11 Deploy | MISSING | CI builds and tests; `psycopg` extra; switchable `DATABASE_URL` | no Dockerfile or Railway config, `$PORT` ignored, ephemeral SQLite, dashboard breaks on Postgres, no migrations, no static serving, hardcoded CORS, still an orphan branch | M-L | one service or two, who owns the Railway project? |

## 15. Risks for the next build

1. **Re-extraction destroys reviewer work.** It writes a new version with every
   status back to `draft`; the database already contains that event (protocol
   1, v2 -> v3). Fix before roles or locking: refuse on a reviewed protocol, or
   merge into it.
2. **The audit trail cannot answer "what changed".** Versions store end state,
   and review drops `reviewer_note` (`protocols.py:193,218-221`). R6 and R7
   both need a real change log.
3. **Data entry has no history at all** (`data.py:99-100`). The hardest R6 gap,
   and it changes the table schema.
4. **The dashboard breaks the moment Postgres is switched on**, because
   `verification/expected_results.py` is sqlite-only and the dashboard imports
   it. The invariant that keeps the comparison honest is what blocks the
   migration: it needs a second implementation, not a shared helper.
5. **Observations reference fields by name string.** Rename a field and
   readings orphan silently, with no FK to catch it.
6. **No migrations.** `create_all` means every schema change for roles, queries
   or audit needs a hand-written path or a dropped database.
7. **Visit segmentation is the least stable step.** The same PDF gave 18 visits
   and 8, 446 fields and 196. Cost, review load and dashboard shape all follow
   from it, and nothing lets a human pin or correct the visit list before the
   per-visit calls go out.
8. **Section mode corrupts quotes.** The `[Section N]` prefix
   (`sections.py:60`) was copied into quotes and cost 6 good fields in protocol
   5. Any cost work that enables section mode must strip it before
   verification, or verification must tolerate it.
9. **Grounding proves existence, not relevance.** 325 fields cited 129 distinct
   quotes on protocol 6, one sentence 18 times; 446 cited 167 on protocol 8,
   one sentence 44 times. R10 cannot rest on match score alone.
10. **The cutoff is invisible at the boundary**: rounding after the comparison
    lets a rejection read `90.0%` against a threshold of 90
    (`verify.py:82-85`).
11. **Section detection is unreliable**: table-of-contents lines parse as
    sections and numbers repeat, so `section_ok` is false for 147 of 325 fields
    on protocol 6, most wrongly. Computed, hidden (`FieldCard.tsx:62`), and not
    to be trusted as a signal.
12. **Running the tests deletes the dev database** (`run.sh:22` does `rm -f
    ecrf.db` while a server may hold the old inode, after which writes fail as
    "readonly database" behind a bare 500). Three live extractions were lost to
    this; this audit used a separate `DATABASE_URL`.
13. **Dead or unreachable code**: `cdash.suggestions` output is rendered but
    not actionable; `POST /api/dashboard/{id}/unsupported` has no caller since
    the panel was removed; `ingest.text_hash` (`ingest.py:168`) is never
    called; `Status.rejected` has never been set by a human.
14. **`@app.on_event("startup")` is deprecated** (`app.py:24`) and breaks on a
    future FastAPI major.
15. **9 protocol rows for 6 distinct documents.** Uploading the same file twice
    creates a second protocol with the same `text_hash`, so review and
    dashboard silently work on divergent copies.

## 16. Open questions

1. Which CDASH / SDTM version and which modules are contractual for the MVP?
2. Will the client's CRF library arrive as a document, spreadsheet or export,
   and does it carry edit checks and codelists?
3. Is the R2 foundation set identical for every study, or per protocol?
4. Should BMI be stored as a derived value, or recomputed on read?
5. Which identity provider, and are 21 CFR Part 11 e-signatures in scope for
   approval and locking?
6. How many reviewers are in the R5 chain, and is the order fixed per study?
7. For R6, is a diffable version chain acceptable, or is a per-field old/new
   change log required for inspection?
8. After a protocol amendment, is a cache keyed on document text hash
   acceptable, or must every extraction be fresh?
9. Which dashboard metrics does the sponsor actually report, and what differs
   per role?
10. What form does the R10 reference eCRF take, and what counts as a match
    between a generated field and a reference field: name, CDASH code, or
    clinical concept?

---

**Method.** Code read directly, every claim cited `path:line`. Run figures come
from the 13 `ecrf_version` rows in the dev database, read from a copy in
`/tmp`. Section 2 was produced mechanically by extracting all 44 file bodies
from `BUILD.md` and diffing them against the tree. Actual token usage, cached
tokens and cost per run are `UNKNOWN` and unrecoverable: `resp.usage` is never
read and nothing persists it. Logging `usage` on both call types into the
version summary would settle every one of those cells on the next run.
