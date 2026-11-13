# eCRF Builder — prototype

BU Spark! Fall 2026 · DS519 · Client: Phoenix Clinical

A clinical trial protocol goes in. Draft electronic case report forms come
out, every generated field carrying a verbatim protocol quote that the code
verifies before a human sees it. A reviewer approves and the form is locked.
Sites enter synthetic data, edit checks raise queries, and values move through
review, approval and sign-off to a study lock. A dashboard reports statistics
that have been independently recomputed.

```
./run.sh          # backend on :8000, frontend on :5173, no API key needed
./run.sh test     # backend tests
```

Then open http://localhost:5173, sign in as `builder@phoenix.demo` with password
`demo1234`, click **Load sample**, then **Extract**. `../instructions.md` walks through
every role and page.

## What runs where

```
protocol.pdf
   │
   ▼
 1 INGEST        pdfplumber, pdffonts gate        backend/ecrf/ingest.py
   ▼
 2 EXTRACT       one call for visits,             backend/ecrf/extract/
                 one per visit, cached prefix     backend/ecrf/pipeline.py
   ▼
 3 VERIFY        quote search, exact then fuzzy   backend/ecrf/verify.py
                 not found → field deleted
   ▼
   FILL GAPS     protocol text, then library,     backend/ecrf/hints.py
                 then plausibility guess          backend/ecrf/cdash.py
                                                  backend/ecrf/guess.py
   ▼
 4 REVIEW        approve, edit, append a version  backend/ecrf/api/protocols.py
   ▼
 5 DATA ENTRY    validated against approved defs  backend/ecrf/api/data.py
                 edit checks raise queries        backend/ecrf/checks/
   ▼
 6 THE CHAIN     monitor review, approval,        backend/ecrf/api/chain.py
                 sign-off, study lock             backend/ecrf/api/queries.py
   ▼
 7 STATS         analysis plan picks the fields   backend/ecrf/api/sap.py
                 fixed registry, refuse the rest  backend/ecrf/stats/
                 independent recomputation        backend/verification/
   ▼
 dashboard, listing, PDFs                         frontend/src/pages/Dashboard.tsx
                                                  backend/ecrf/api/reports.py
```

## Hosting

Vercel with a Supabase database: see [DEPLOY.md](DEPLOY.md).

## Model backends

The model is a config value. `ECRF_BACKEND=mock` replays a recorded run on
the bundled sample and needs nothing. `ECRF_BACKEND=openai_compat` talks to
any provider that speaks the OpenAI chat format: OpenAI, vLLM on SCC, Groq,
OpenRouter, Gemini. See `.env.example`.

## The sample protocol

`backend/data/sample/PHX-401-201_protocol.pdf` is synthetic. Two things are
planted so the safety checks visibly fire:

- Section 7.3.2 says 5 minutes of rest, Appendix B says 10. The model
  flags **conflicting** rather than picking.
- There is no heart rate requirement anywhere. The recorded extraction
  fabricates one, and the grounding check deletes it. You will see it in the
  **Dropped by verification** panel with a match score of 57.

For a real public protocol: `python backend/scripts/fetch_ctgov_protocol.py`.

## Layout

```
backend/
  ecrf/            the pipeline and API
  data/            cdash library, sample protocol, recorded fixture
  verification/    independent stats. Imports NOTHING from ecrf/.
  scripts/         fetch a ClinicalTrials.gov protocol
  tests/
frontend/
  src/api/         types.ts mirrors the backend schema; client.ts owns URLs
  src/styles/      tokens.css is the only place colours and type are defined
  src/components/  Layout, Badge, FieldCard, Stat, charts/
  src/pages/       Login, ChangePassword, Admin, Protocols, Visits, Review, Checks,
                   Sites, DataReview, Sap, Dashboard, Listing, Queries, Notifications,
                   Studies, Patients, DataEntry, Glossary
  public/logo.svg  REPLACE with the Phoenix Clinical logo
```

## Rules that are not negotiable

- No real patient data. Synthetic or approved de-identified only.
- No Phoenix material to unapproved services.
- No generated form used without qualified approval.
- No unsupported analysis attempted. Refuse instead.
- `verification/` imports nothing from `ecrf/`.

## Credits

Architecture draft by the team's systems member informed the CDASH
mapping layer and the structured document representation.
