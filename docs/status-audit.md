# Status audit: Phoenix eCRF Builder

Read-only audit, 2026-11-05, judged from the code. "Ran" means I exercised the behaviour through the API on a throwaway SQLite database with `ECRF_BACKEND=mock`. No paid API was called. Backend paths are relative to `ecrf-prototype/backend/`.

## 1. Git state

- **Branch:** `sprint2`. The working tree is not clean.
- **Modified, uncommitted:** `frontend/src/pages/Login.tsx` and `frontend/src/styles/global.css`, which remove the login quick-fill.
- **Untracked:** `Demo script.pdf`, `Midterm script.pdf`, `Project context prompt.md`, `NCT01841281_asthma_protocol.pdf`, `NCT02251431 Diabetes Heart and Kidney Trial.pdf`, `midterm-assets/`, and `test_protocols/30-8 test 1.pdf` and `30-8 test 2.pdf`.
- **Local branches:** `demo-noco`, `demo/failing-lint`, `main`, `spark-test`, `spark-test-demo-failing-lint`, `spark-test-noco`, `sprint2`.

| Remote | Repository | Visibility | Live branches, checked today |
|---|---|---|---|
| `public` | jigark712/phoenix-ecrf-builder | Public | `main` |
| `origin` | Priyanshusingh09876/Spark-test | Not checked | `demo/failing-lint`, `main` |
| `spark` | BU-Spark/se-phoenix-clinical | Private | `demo-test`, `dev`, `fix/ci-skip-ecrf-prototype`, `incident/next-security-recovery-20261022`, `main`, `skeleton-branch`, `spark-test`, `spark-test-demo-failing-lint`, `your-branch-name` |

**Commits on `sprint2` not on `spark-test` (23):**

```
8303ddb Glossary page: every word on the screens, in plain language, from the sidebar foot
56f8b93 Add instructions.md: running the prototype on a new machine
4d87d4f QTcF is matched by name only
882f855 Derived values computed in code, and a readable section panel
62f86ed Value rules a site cannot bypass, and warnings before locking
06eeb64 Yes/no fields: two explicit answers, blank means unanswered
00a2ea6 Queries about the study, a patient or a visit, not only one value
2540151 New query button on the Queries page, for both portals
7dfe7d1 Queries run both ways
deec90c Find a cited section by heading or phrase when the number is missing
964749c Patient registration form: subject ID, initials, year of birth, sex, enrolment date
c94e8ce One sponsor role: builder and approver merged
82c6eaf Edit button on the Review page: name, type, unit, range, repeats, required, choices
0338282 Keep a visit's valid fields when the model writes one malformed field
29bc70a Add test_protocol6 (NCT02251431, 31 pages) for an uncached demo run
244883e Fill flagged fields from the protocol text first, then library, then guess; switch to gpt-6-luna
3b5104f Guess a range for flagged numeric fields, and a filter bar on Review
e710cfe Suggest units and ranges from the CDASH library on flagged fields
389b2de Stage 5: queries on entered data
e459110 Stage 4: fewer API calls, lower cost
beb0e35 Stage 3: form lock, site assignment, patients, and the data approval gate
b1ea7a4 Stage 2: login, organisations, roles, and two portals
49275ee Stage 1: Alembic, safer tests, and the small fixes later stages rely on
```

**Pushed or merged:**

- No remote has a `sprint2` branch.
- 22 of the 23 commits are on `public/main`. `8303ddb` is not pushed anywhere.
- None of the 23 are on `spark/spark-test`, which sits at the base of `sprint2`, or on `origin`.
- `main`, `origin/main`, and the local copies of `spark/main` and `spark/dev` share no common ancestor with `sprint2`.
- Live `spark/main` (`3268213`) and `spark/dev` (`b244c6a`) have moved since the last fetch. I did not fetch, so they are not compared.
- CI in `.github/workflows/ecrf-ci.yml` triggers only on `main` and `spark-test`, so pushes to `sprint2` do not run it.

## 2. Test results

| Check | Result |
|---|---|
| Backend `pytest`, temp DB, mock backend | **143 passed, 0 failed**, 67.6 s |
| Frontend `npm run build`, output sent to a temp folder | **Passes** |
| `eslint` | Clean |
| `ruff` | Clean |
| `alembic check` on a temp DB | No differences from the models |
| Frontend unit tests | None exist |
| Postgres | **Could not run.** Not installed on this machine, and no test uses it |

`backend/ecrf.db` and `midterm-assets/demo/db/demo.db` were not modified by any of this.

## 3. Item status

### 3.1 Sprint 2, stage 1. Housekeeping

| Item | Status | Evidence | What's missing |
|---|---|---|---|
| Alembic migrations exist and match the models | Built | `migrations/versions/0001` to `0009`. `alembic check` finds no differences | |
| `run.sh test` no longer deletes the dev DB | Built | `run.sh:21-27` only runs pytest. `tests/conftest.py` sets a temp `DATABASE_URL`. `ecrf.db` unchanged after a direct pytest run | |
| Rounding bug fixed | Built | `ecrf/verify.py:96` rounds before comparing. `test_threshold_compares_the_rounded_score` | |
| `[Section N]` prefix stripped | Built | `ecrf/verify.py:37,91` `clean_quote`. `test_section_label_is_stripped_before_matching` | |
| Duplicate PDF upload detected | Built | `api/protocols.py` `upload` matches `text_hash` within the org. `test_duplicate_upload_returns_the_existing_protocol`. Ran: a renamed copy returned `already_loaded` | |
| Re-extraction returns 409 unless `force` | Partial | `api/protocols.py` `_guard_extract`. `test_reextraction_is_refused_after_review_unless_forced`. Ran: reviewed 409, with force 200, locked 409 even with force | Refuses only after a human review. Ran: an unreviewed draft re-extracts with no `force` and returns 200 |
| FastAPI lifespan handler | Built | `api/app.py:17-26`. Refuses to start on a database that is behind | |

### 3.2 Sprint 2, stage 2. Login and roles

| Item | Status | Evidence | What's missing |
|---|---|---|---|
| `organisation`, `user`, `session` tables | Built | `ecrf/storage/models.py`, `migrations/versions/0002_identity.py` | |
| scrypt password hashing | Built | `ecrf/auth/passwords.py` | |
| httpOnly session cookie | Built | `ecrf/auth/sessions.py` `start`. Only the token's sha256 is stored | |
| 429 after 5 failed logins | Built | `sessions.too_many_failures`, `api/auth.py` `login`. `test_five_failures_in_a_row_lock_the_email_out`. Counter is in memory, per process | |
| Roles builder, approver, site_staff | Partial | `ecrf/auth/permissions.py` has `sponsor` and `site_staff`. `migrations/versions/0006_one_sponsor_role.py` | `builder` and `approver` do not exist. They were merged into `sponsor` on purpose on 29 October |
| Permissions table and `require(perm)` used on routes | Built | `ecrf/auth/permissions.py`. Route walk: 35 of 37 router routes use it, and the other two are login and logout. `test_matrix` | |
| Org scoping returns 404 outside scope | Built | `ecrf/auth/scope.py` `protocol_or_404`. `test_another_sponsor_cannot_see_phoenix_protocols`. Ran: Mercy got 404 on a study assigned to Boston General. One exception: `POST /api/dashboard/{id}/unsupported` skips scope | |
| Demo accounts seeded | Built | `ecrf/auth/demo.py`, `scripts/seed_demo.py`, `run.sh:34` | |
| Login page, separate sponsor and site views | Built | `frontend/src/pages/Login.tsx`, `App.tsx` `Portal`, `components/Layout.tsx` | |

### 3.3 Sprint 2, stage 3. Lock, sites, patients, approval

| Item | Status | Evidence | What's missing |
|---|---|---|---|
| Form lock, refused while draft or flagged | Built | `api/protocols.py` `lock`, `_lock_blockers`. `test_lock_needs_every_field_decided_and_then_freezes_the_form`. Ran: 409 while undecided | |
| Locked forms cannot be edited, API checked | Built | Ran: after lock, review, extract, extract with force, PUT visits, extract/visits with force, and extract/fields with force all return 409 | |
| Assign sites to a protocol | Built | `api/sites.py`, `frontend/src/pages/Sites.tsx`. `test_sites_see_only_assigned_locked_studies` | |
| Server-generated patient codes | Built | `api/studies.py` `create_subject`. `test_subject_codes_are_made_by_the_server_and_owned_by_the_site`. Ran: got `BGH-001` | |
| Observation status entered, approved, queried | Built | `models.py` `Observation.status`, `api/data.py`, `api/queries.py` | |
| `observation_history` with old and new values | Built | `models.py` `ObservationHistory`, `api/data.py` `record_change`. `test_edits_write_history_and_approved_values_are_frozen`. The endpoint exists, but no screen calls it | |
| Stats read approved rows only | Built | `ecrf/stats/registry.py` `load_frame`. `test_stats_count_only_approved_rows_in_both_implementations` | |
| Independent verifier reads approved rows only | Built | All three queries in `verification/expected_results.py` filter `status='approved'`. Same test | |

### 3.4 Sprint 2, stage 4. Cost

| Item | Status | Evidence | What's missing |
|---|---|---|---|
| Usage and estimated cost logged on every LLM call | Partial | `ecrf/extract/openai_compat.py` `_chat` logs tokens. `llm_call.usage_json` stores them. `extract/base.py` `Usage.cost_usd`. `test_usage_is_summed_and_priced` | Cost is computed per run, not per call. Calls answered from the cache are counted but not logged |
| `llm_call` cache keyed by request hash, repeat run costs $0 | Built | `ecrf/extract/cache.py`. `test_second_identical_run_makes_no_api_calls` | |
| `prompt_cache_key` and `prompt_cache_retention` | Built | `openai_compat.py` `_optional_kwargs`. `test_openai_gets_cache_hints_and_an_output_cap` | |
| `max_completion_tokens` with fallback, truncation refused | Built | `openai_compat.py` `_drop_rejected`, `_chat`. `test_truncated_output_is_refused`, `test_rejected_parameter_is_dropped_and_the_run_continues` | |
| `reasoning_effort` and `max_retries=3` | Built | `openai_compat.py` `__init__`, `_optional_kwargs` | |
| Confirm-visits step before per-visit calls | Built | `api/protocols.py` `extract_visits`, `put_visits`, `extract_fields`. `frontend/src/pages/Visits.tsx`. `test_two_step_extraction_lets_a_person_fix_the_visits` | |
| `EXTRACT_STRATEGY=per_form` works on the mock | Built | `ecrf/pipeline.py` `run_fields`, `extract/mock.py` `plan`, `fields_for_form`. `test_per_form_covers_the_same_grid_as_per_visit` | |

### 3.5 Sprint 2, stage 5. Queries

| Item | Status | Evidence | What's missing |
|---|---|---|---|
| Sponsor raises, site answers and may correct, sponsor closes | Built | `api/queries.py`, `frontend/src/pages/Queries.tsx`. `test_full_flow_raise_answer_with_correction_close_approve` | |
| Open query blocks approval | Built | `api/data.py` `approve_data` returns 409 for `queried` rows. Applies to queries about one value | |
| Count badges in the UI | Built | `components/Layout.tsx` sidebar badge from `for_me`, `pages/Queries.tsx` tab counts | |

### 3.6 Client asks from meeting 1

| Item | Status | Evidence | What's missing |
|---|---|---|---|
| Forms follow CDASH, codes from the YAML library | Partial | `ecrf/cdash.py` `enrich`, `data/cdash_library.yaml` with domains DM, VS, EG, LB, AE | Codes attach only when a name matches those 5 domains. In the stored NCT02251431 run, 9 of 13 Day 1 fields have no code |
| Foundation form first | Missing | No foundation form in code or prompts. These fields appear only if the model extracts them | The whole form. BMI calculation exists separately in `ecrf/derive.py` and `frontend/src/derive.ts`, and needs height and weight on the same visit |
| Comments, sticky notes, field metadata | Partial | Metadata is in `ecrf/schema.py` `FieldDef`. A note per review is stored on the version | No field comments or sticky notes. `reviewer_note` at `api/protocols.py:411` is accepted and thrown away. Ran: the note did not appear in the draft |
| Audit trail with old and new values, form edits and data entry | Partial | Data entry: `ObservationHistory`. Form edits: full snapshots through `db.save_version` | No field-level old and new values for form edits. No screen shows value history. Approving and un-approving write no history row. Ran: `approved_by` was cleared and history showed only the value change |
| Dashboard shows real metrics from approved data | Partial | `api/dashboard.py` reads approved rows. Extraction counts are real | `stats/calculations.py:14-16` hard-codes Systolic Blood Pressure, Day 1 and Week 12. Percent missing infers expected slots from approved rows, not the form. `calculations.py:7` still says PLACEHOLDER SET |

### 3.7 Sprint 3 and deployment

| Item | Status | Evidence | What's missing |
|---|---|---|---|
| Verifier works on Postgres without importing `ecrf/` | Missing | `verification/expected_results.py:19`. Ran: raises `RuntimeError` on a Postgres URL | Any non-SQLite support. `api/dashboard.py` calls it whenever approved rows exist, so the dashboard would return 500 there |
| Does `verification/` import from `ecrf/`? | Built | No. Every import: `collections.defaultdict`, `pathlib.Path`, `sqlite3`, `sys` | |
| `$PORT` respected | Missing | `run.sh:36` hard-codes 8000. Nothing reads `PORT` | All of it |
| CORS configurable by env var | Missing | `api/app.py:33` hard-codes two localhost origins | All of it |
| Backend serves the built frontend | Missing | No `StaticFiles`, `FileResponse` or `mount` anywhere | All of it |
| Railway config present | Missing | No Procfile, `railway.json`, Dockerfile or similar in `git ls-files` | All of it |

### 3.8 Azem's sprint list

| Item | Status | Evidence | What's missing |
|---|---|---|---|
| Optimised LLM calls | Built | `extract/cache.py`, confirm-visits step, provider cache hints, `sections.py` above the token limit. Pass one still sends the whole protocol (`pipeline.plan`) | |
| Role-based auth with login page | Built | See 3.2 | |
| Custom CRF library support | Partial | `ecrf/cdash.py` `library` reads one YAML file, transcribed from Phoenix's document | No way for a user to add a library or a field. Ran: a review naming a new field was ignored |
| RapidFuzz accuracy evaluation | Missing | No script, test or report measures threshold 90. `verify.py:12` and `config.py:39` call it a placeholder | All of it |
| DB schema documented | Partial | Docstrings in `storage/models.py`. `AUDIT.md` section 7 and `BUILD.md` cover 3 tables and predate stage 2 | No document covers `organisation`, `user`, `session`, `llm_call`, `protocol_site`, `subject`, `observation_history` or `query` |

### 3.9 Anything else

**Features not in the lists above:**

- Field editor on Review, for name, type, unit, range, repeats, required and choices.
- Gap filling from protocol text (`hints.py`) and plausibility guesses (`guess.py`), with labels and a filter bar.
- Derived values in code: BMI, BSA, mean arterial pressure, pulse pressure, QTcF and eGFR.
- Date and yes/no value rules, and warnings before locking.
- Queries both ways, about a study, patient, visit or value.
- Patient registration details, cited-section lookup, salvage of malformed model fields, and a Glossary page.
- "Seed 20 synthetic subjects" button, and a CI workflow.

**Dead code and stubs.** There are no TODO or FIXME markers in the code.

- `ecrf/api/dashboard.py:111-121`: the `unsupported` route. Ran: a registered name returns 200 with `{"error":"should not reach here"}`, and an unknown protocol returns 500. It has no scope check, and the session from `next(db.get_session())` is never closed.
- `ecrf/api/protocols.py:411`: `reviewer_note` is accepted and discarded.
- `ecrf/api/queries.py:106`: the `.column_descriptions` check is always truthy and does nothing.
- `ecrf/api/data.py:237`: `GET /api/data/{id}/subjects` has no frontend caller.
- `frontend/src/api/client.ts:56,87`: `api.extract` and `api.history` have no callers.
- `frontend/src/components/FieldCard.tsx:130`: `section_ok` is computed but deliberately not shown.

**Broken or risky.** Each was run unless marked as read.

1. **Upload path traversal.** `api/protocols.py:80` trusts the filename. A file named `../escaped.pdf` was written outside the upload folder. Needs a signed-in sponsor.
2. **Upload can replace a stored PDF.** The file is written before the duplicate check, so a different document with the same name overwrites it, and a scanned one deletes it (`:86`). Read, not run.
3. **A site can withdraw a sponsor's approval alone.** It raised a query on an approved value, edited the value through `/api/data/enter`, and closed its own unanswered query. The value returned to `entered`, so it leaves the stats until re-approved.
4. **Query corrections skip entry rules.** A yes/no correction was stored as `true`, not `Yes` (`api/queries.py:217`). The derived-value check is not called on this path (read, not run).
5. **Green pass on an unavailable stat.** Mean change returned null from both sides and `pass: true`.
6. **Seed button.** It returned 500 when `BGH-001` was registered with no readings. On a protocol with no form it added 731 rows, about 70% marked approved by `seed`.
7. **Unassigning a site.** The site got 404 on its study while its 16 rows remained, with no warning.
8. **Client-derived data on a public repo.** `data/cdash_library.yaml` is on `public/main`, and its header says codelists and ranges are "taken from the client document". The document itself is not tracked.
9. **The running app is in demo mode.** `:8000` is using `midterm-assets/demo/db/demo.db`, not `ecrf.db`.
10. **Forced re-extraction does not refresh the cache.** `extract/cache.py:43` skips an existing key, although `extract/base.py` says writes still happen. Read, not run.
11. **Lock updates a row in place.** `lock` changes `state`, `locked_by` and `locked_at` on the version row. Field content is unchanged.
12. **Stale docs.** `CLAUDE.md` still says `run.sh test` deletes `ecrf.db`, and the code no longer does. `README.md` lists only four of the pages.
13. **Deployment defaults.** The default password is `demo1234` (`config.py:92`), `run.sh` seeds accounts when the user table is empty, and `/docs` is open. Read, not run.

## 4. Summary counts

| Section | Built | Partial | Missing |
|---|---|---|---|
| Stage 1. Housekeeping | 6 | 1 | 0 |
| Stage 2. Login and roles | 8 | 1 | 0 |
| Stage 3. Lock, sites, patients, approval | 8 | 0 | 0 |
| Stage 4. Cost | 6 | 1 | 0 |
| Stage 5. Queries | 3 | 0 | 0 |
| Client asks from meeting 1 | 0 | 4 | 1 |
| Sprint 3 and deployment | 1 | 0 | 5 |
| Azem's sprint list | 2 | 2 | 1 |
| **Total (50 items)** | **34** | **9** | **7** |

## 5. Top 5 gaps that block a working demo

1. **The app cannot be hosted.** `$PORT`, CORS configuration, serving the frontend and Railway config are all missing, so Phoenix has nothing to open. `sprint2` is also not on the BU Spark remote.
2. **The verifier fails on Postgres.** It raises on any non-SQLite URL, so the dashboard would return 500 once approved data exists on a hosted Postgres database.
3. **Dashboard statistics are tied to the sample protocol.** On a real protocol, mean change shows "not available" with a green pass, and percent missing does not use the form.
4. **The foundation form does not exist.** The client asked for consent, demographics, height, weight and BMI first. Today those fields appear only if the model extracts them.
5. **The form audit trail and field comments are incomplete.** Form edits have no field-level old and new values, `reviewer_note` is discarded, value history has no screen, and approvals are not recorded.
