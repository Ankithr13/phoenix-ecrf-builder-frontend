# Continuous integration

This document covers the CI pipeline only. For the project itself, what it
does and how to run it locally, see [README.md](README.md).

The project lives on the `spark-test` branch of this repository.

## The tool

**GitHub Actions.** The code is already hosted here, so Actions needs no
extra account, no runner to host and no webhook to configure, and the
results appear on every commit and pull request where a reviewer is
already looking. The whole pipeline is one file:
[.github/workflows/ecrf-ci.yml](.github/workflows/ecrf-ci.yml), registered
as the workflow **eCRF CI**.

The project has two halves, a Python backend and a TypeScript frontend, so
the pipeline has to run both toolchains in a single job graph.

## What it does

Three jobs. Linting and testing have nothing to do with each other, so they
run at the same time. The build waits for both.

```
lint ─┐
      ├─► build
test ─┘
```

| Job | Tool | What it checks | Fails when |
| --- | --- | --- | --- |
| Lint (ruff + eslint) | `ruff` over `ecrf-prototype/backend`, `eslint` over `ecrf-prototype/frontend` | style, unused imports, import order, obvious mistakes | any lint error |
| Unit tests (pytest) | `pytest` | the extraction pipeline end to end against a recorded fixture | any test fails |
| Build frontend | `tsc` then `vite` | the whole project type-checks, then bundles | a type error or a bundle error |

Two extras worth knowing about. The test job writes a pass and fail table
into the run summary and uploads its JUnit XML as the artifact
`pytest-results`, so a failure can be read without opening the log. The
build job uploads the bundle as `frontend-dist`, which is the point of
building at all.

The tests run with `ECRF_BACKEND=mock`, which replays a recorded extraction
of the bundled sample protocol. No API key is stored in the repository and
the suite makes no network calls.

### The part that matters

The build job declares `needs: [lint, test]`. A bundle is therefore only
ever produced from code that passed every check. This is enforced, not
just documented:

| Run | Lint | Tests | Build |
| --- | --- | --- | --- |
| [Push to `spark-test`](https://github.com/BU-Spark/se-phoenix-clinical/actions/runs/38981845770) | passed, 23:31:27 | passed, 23:31:39 | **started 23:31:42**, passed |
| [Pull request #10](https://github.com/BU-Spark/se-phoenix-clinical/pull/10/checks) | **failed** | passed | **skipped, 0 seconds** |

In the first run, lint and the tests ran side by side and the build started
three seconds after the slower of the two finished. In the second, a branch
with one deliberate unused import, the tests passed and the build still
never ran. Passing tests alone are not enough.

Pull request #10 exists only to show that. It is not for merging.

## How to trigger it

Any of these starts a run:

- **Push to `spark-test` or `main`.** This is the normal path.
- **Open or update a pull request** into either branch.
- **Start it by hand.** Actions tab, eCRF CI in the left sidebar, then
  Run workflow. By API:
  ```bash
  gh api -X POST \
    repos/BU-Spark/se-phoenix-clinical/actions/workflows/ecrf-ci.yml/dispatches \
    -f ref=spark-test
  ```
- **Re-run an existing run** from the Re-run all jobs button on any run or
  pull request checks page.

A full run takes about 70 seconds.

The same checks run locally, and running them before pushing is faster than
waiting for the pipeline:

```bash
cd ecrf-prototype/backend  && ruff check . && pytest -v
cd ecrf-prototype/frontend && npm run lint && npm run build
```

## Challenges

**The workflow file name was already taken.** This repository's `main`
branch has a `.github/workflows/ci.yml` belonging to an earlier project.
GitHub identifies a workflow by its path, not by the `name:` inside it, so
our runs were being filed under that other workflow's name in the Actions
tab. Renaming ours to `ecrf-ci.yml` gave it its own entry and left the
other project's file untouched.

**Nothing ran for the first few pushes.** The triggers listed only `main`,
which is where a workflow normally lives, but this project sits on
`spark-test`. Pushes landed and no run appeared, which looks exactly like
Actions being broken. Both triggers now list `spark-test` alongside `main`.

**The linter rejected correct FastAPI code.** `ruff` flags `Depends()` and
`File()` in a function signature as B008, a mutable default argument, and
that is the idiom FastAPI requires. Rather than disable the rule set, the
rules are pinned explicitly in
[pyproject.toml](ecrf-prototype/backend/pyproject.toml) with B008 ignored
and a comment saying why, so a future ruff release cannot change what CI
enforces without someone choosing it.

**ESLint would not install.** `@eslint/js` version 10 against `eslint`
version 9 fails `npm ci` with an ERESOLVE peer dependency error, which
fails the job before a single file is linted. Pinning both to matching
majors fixed it.

**The build caught something the tests could not.** `tsc` runs with
`noUnusedLocals`, and an unused import left behind after a refactor broke
the build while every test still passed. That is the argument for treating
the build as a check rather than a packaging step.

**Proving the gate needed a failure on purpose.** A pipeline that is always
green does not show that the ordering is enforced, only that it is
declared. Pull request #10 adds one unused import so the lint job fails,
and the skipped build is the proof.

**One local trap, for anyone running the suite on their machine.**
`./run.sh test` deletes `backend/ecrf.db`. If the dev server is running it
keeps a handle on the deleted file and every later write fails with
"attempt to write a readonly database", which surfaces as a bare HTTP 500.
Stop the server first, or point the tests at a different `DATABASE_URL`.
CI is unaffected, since every run starts from a fresh checkout.
