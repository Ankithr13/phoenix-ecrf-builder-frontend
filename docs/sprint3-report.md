# Sprint 3 report

For Tarushi, before testing locally. Everything is on branch `sprint3`, one commit per
stage. Nothing has been pushed or merged. All testing used the mock extractor, so no
paid API calls were made.

## Result

| | Passed | Skipped |
|---|---|---|
| Start of sprint | 143 | 0 |
| End of sprint | 279 | 1 |

The one skip is `test_ec_011`: that check needs an intervention form this system does
not model. Lint, build, `alembic check` and the verifier import check are all clean.

## What was built

| Stage | Built | Tests after |
|---|---|---|
| 1. Fixes from the audit | The 15 audit items, including upload safety, query corrections following entry rules, no green pass on an unavailable statistic, and `prod` refusing a default secret | 159 |
| 2. Put it online | **Skipped at your request.** All of its work was removed | |
| 3. Roles and admin | Eight roles and the permission matrix, admin panel, access log, first-login password change, chain switches | 203 |
| 4. Foundation form and audit | Foundation form on every protocol, visit date on every visit, field comments, form audit trail, value history screen | 213 |
| 5. Data entry rules | Submit, Not done / Not applicable / Unknown, reason for change, edit check engine, built-in and custom checks, system queries, lab ranges | 236 |
| 6. The approval chain | Query lifecycle with cancel, monitor review, investigator sign-off, study lock, notifications | 262 |
| 7. Results and reports | Analysis plan page, the five statistics, independent verifier, three dashboard tabs, data listing with export, two PDFs | 276 |
| 8. Documents | This report, the database schema, roles, edit checks, analysis plan and completion guide, plus refreshed READMEs and instructions | 279 |

## Before you test: what changed under you

- **The server on port 8000 is running old code.** Restart with `./run.sh`.
- **`./run.sh` migrates `backend/ecrf.db`.** Tested on a copy: revision 0009 to 0015, with
  all 14 protocols, 58 form versions and 2,246 values kept. The 4 existing accounts,
  all on the old `sponsor` role, became data managers. Back up the file if it matters.
- **`demo.sh` no longer works as it was.** Its database is behind the migrations, so the
  backend refuses to start. It was not changed.
- **The midterm demo script is out of date.** "A BMI of 52 is refused" no longer happens:
  a value out of range now saves and raises a query. The builder can no longer lock the
  form; the data manager does. Under `npm run dev`, the login page lists the demo accounts again.
- **A real `.env` needs renaming.** Costs show "not configured" until `PRICE_*` becomes
  `LLM_PRICE_*`.

## Not verified

- **A real protocol through Stages 3 to 7.** All of it ran on the mock sample, since a
  real run needs a paid call. Real protocols will have stranger field names and more
  visits, and built-in checks that bind by name may miss or misfire.
- **Postgres.** Not tested, and it would not fully work: the independent verifier reads
  SQLite only, so the dashboard's Results would fail. A `%` in a `DATABASE_URL` also
  crashes migrations; that was found in the removed Stage 2 and is not fixed.
- **The statistics against a statistician's review.** The app and verifier agree with
  each other and with values worked by hand. Nobody has checked that these are the right
  analyses for a trial.
- **`per_form` against `per_visit` on a real protocol.** Needs a paid call and your OK.
- **The client's documents.** `docs/client/` was not present, so the summaries inside
  SPRINT3.md were the source. Nothing was checked against the originals.
- **The quote threshold of 90.** Still a placeholder, never tuned.
- **Browsers and devices.** Checked with scripted Chrome at desktop width. Other browsers,
  phone widths and screen readers were not tried. The frontend has no automated tests;
  those scripts were throwaway and are not in the repo.
- **CSV and PDF downloads through the browser's save.** The buttons were not followed to a
  saved file. The same responses were fetched in the browser and opened, and tests cover
  the routes.
- **Long protocols in the PDFs.** Only the sample was rendered.
- **Several people at once.** Nothing tested two users editing the same value together.
- **CI.** `.github/workflows/ecrf-ci.yml` was not run, because nothing was pushed.

## Assumptions to confirm with the client

Most important first. Each stage's section in `sprint3-progress.md` has the rest.

**Statistics**

1. Results are pooled, because there are no treatment arms or analysis populations.
2. Repeats within a visit are averaged per subject first. This came from the sample protocol and now applies to every field.
3. "First dosing" has no field. A safety row's baseline visit stands in for it, otherwise the subject's first visit date is used.
4. A safety item needs an AE start date field. Without one there is no TEAE count.
5. Percent missing counts Not done and Not applicable as missing, out of all registered subjects.

**The chain**

6. A value out of range saves and raises a query, because the sprint says only format checks are hard.
7. Every required field raises its own query when blank, so a half-empty visit raises many at once.
8. Study lock also needs every entered value approved, which goes further than the sprint's wording.
9. Sign-off is blocked by any open query on the patient, not only on that visit.
10. A query a person closed stays closed until its value changes.
11. "One page per visit" in the blank eCRF means each visit starts a new page. A long one carries on.

**Roles and data**

12. Whoever can close a query can also reply in words to one a site raised, since the matrix gives sponsors no `query.answer`.
13. The casebook needs `listing.view`, so read-only and the builder cannot get one. Casebook downloads are also on the access log.
14. Sex, Race and Ethnicity on the Foundation form use the library's codelists, so Sex is M, F, U, UNDIFFERENTIATED. Patient registration still uses Male and Female.
15. Lab ranges come from MedlinePlus, marked `unconfirmed`. They are offered on the review card and never applied without a click.
16. `data/cdash_library.yaml`, built from the client's document, is on the public `public/main` repo. Please check that is acceptable.

## The top 5 things to do next

1. **Run one real protocol end to end**, with your OK for the paid call. It is the biggest unknown, and it would also settle `per_form` against `per_visit`.
2. **Take these assumptions to the client**, statistics first. Arms and populations are the largest gap between this and a real analysis.
3. **Trim pass one to the schedule of activities plus headings.** It still sends the whole protocol, which is the main cost and the reason small providers fail.
4. **Bring hosting back**, once local testing is done. That means the verifier on Postgres, the `%` fix, and a real hosted database.
5. **Tune the quote threshold** against a form the client has approved. It is what the project's main safety claim rests on, and it is still a guess.
