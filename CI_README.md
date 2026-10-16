# eCRF Builder: CI pipeline

A clinical trial protocol goes in as a PDF. Draft case report forms come
out, one per study visit, with every field carrying the sentence from the
protocol that requires it. Code then searches the protocol for that
sentence and deletes any field whose quote is not there.

The project lives on the `spark-test` branch. For setup and how to run it,
see [README.md](README.md).

## The CI tool

**GitHub Actions.** The code is already hosted here, so there is no runner
to host, no account to add and no webhook to wire up, and results show on
every commit and pull request where someone is already looking. The whole
thing is one file,
[.github/workflows/ecrf-ci.yml](.github/workflows/ecrf-ci.yml), registered
as the workflow **eCRF CI**.

## Tasks implemented

What was built, in the order a protocol moves through it.

| Task | What it does |
| --- | --- |
| Protocol ingestion | Reads the PDF into text, tables and numbered sections. Refuses scanned files with no text layer instead of returning nothing. |
| Field extraction | Two model calls. The first asks what the visits are, the second asks what has to be recorded at each one. Any provider speaking the OpenAI chat format works, and an offline mock replays a recorded run. |
| Grounding check | Every field must quote the protocol. Code, not a model, searches the document for that quote and deletes the field if the match scores under 90. This is the part that stops the model inventing fields. |
| Standard codes | Attaches CDASH names and domains from the client's library. Deterministic, and it never adds a field. |
| Review and approval | A reviewer sees each field as draft or flagged, with its quote, and approves. Every approval writes a new version rather than editing the old one, so the history is an audit trail. |
| Data entry | Synthetic subject data is entered through the approved forms only. No real patient data anywhere. |
| Dashboard | A fixed set of approved statistics. A separate script that shares no code recomputes each one, and the two numbers are shown side by side. |
| CI pipeline | Lint, test and build on every push, described below. |

## The pipeline

Three jobs. Linting and testing have nothing to do with each other, so they
run at the same time. The build waits for both.

```
lint ─┐
      ├─► build
test ─┘
```

| Job | Tool | Fails when |
| --- | --- | --- |
| Lint (ruff + eslint) | `ruff` over the Python backend, `eslint` over the TypeScript frontend | any lint error |
| Unit tests (pytest) | `pytest` against a recorded fixture, no API key, no network | any test fails |
| Build frontend | `tsc` type check, then a `vite` bundle | a type error or a bundle error |

The test job writes a pass and fail table into the run summary and uploads
its JUnit XML as `pytest-results`. The build job uploads the bundle as
`frontend-dist`.

The build declares `needs: [lint, test]`, so a bundle only ever comes from
code that passed both. That is enforced, not just written down:

| Run | Lint | Tests | Build |
| --- | --- | --- | --- |
| [Push to `spark-test`](https://github.com/BU-Spark/se-phoenix-clinical/actions/runs/38981845770) | passed, 23:31:27 | passed, 23:31:39 | **started 23:31:42**, passed |
| [Pull request #10](https://github.com/BU-Spark/se-phoenix-clinical/pull/10/checks) | **failed** | passed | **skipped, 0 seconds** |

The build started three seconds after the slower of lint and test finished.
In the second run, a branch with one deliberate unused import, the tests
passed and the build still never ran. Pull request #10 exists only to show
that and is not for merging.

## How to trigger the pipeline

Any of these starts a run:

- **Push to `spark-test` or `main`.** This is the normal path.
- **Open or update a pull request** into either branch.
- **Start it by hand.** Actions tab, eCRF CI in the sidebar, Run workflow.
  By API:
  ```bash
  gh api -X POST \
    repos/BU-Spark/se-phoenix-clinical/actions/workflows/ecrf-ci.yml/dispatches \
    -f ref=spark-test
  ```
- **Re-run an existing run** from the Re-run all jobs button.

A full run takes about 70 seconds. The same checks run locally:

```bash
cd ecrf-prototype/backend  && ruff check . && pytest -v
cd ecrf-prototype/frontend && npm run lint && npm run build
```

## Challenges faced

**No API key for the first few weeks.** The client key arrived late, so the
pipeline was built against a recorded extraction that replays offline. Work
carried on, and switching to the real key was a change to one config file.

**Free tiers are too small for real protocols.** Groq allows 8,000 tokens a
minute. The first call sends the whole protocol to ask what the visits are,
so anything over roughly 12 pages failed before it started. Trimming that
first call is the main thing still to fix.

**Requests were rejected that should have fit.** A 5,500 token prompt came
back as 8,228 and over the limit. The provider counts the output it
reserves, not only what you send. Capping the output fixed it, and the
arithmetic made no sense until we worked that out.

**A model was retired mid-testing.** Calls started returning 404 with no
warning. We listed the provider's models and moved to one still running.

**The same protocol gives different answers.** Uploaded twice, one run
found 18 visits and the other 8, because the titration weeks were split in
one and collapsed in the other. Field counts came out 446 and 196. The
extraction is not random, but deciding what counts as a visit is the least
stable step and everything downstream depends on it.

**A quote being real does not make it relevant.** The grounding check
proves the sentence is in the protocol, nothing more. On the 76 page
protocol, 325 fields cited 129 different sentences, and one sentence was
cited 18 times. It catches invented citations, not lazy ones.

**Section numbers come from the table of contents.** The parser reads those
lines as real sections, so the section cross check disagreed with about
half the fields on a long protocol, most of them wrongly. It still runs but
is hidden from the reviewer rather than shown as a false warning.

**Running the tests wiped the working database.** The test script deletes
the dev database, and a running server keeps a handle on the deleted file,
so every later write fails with a readonly database error that surfaces as
a bare 500. Three live extractions were lost before we understood it. CI is
unaffected since each run starts from a fresh checkout.
