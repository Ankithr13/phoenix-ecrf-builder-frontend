# Manual study organisation

Sponsors create studies with a name and a study ID. Each protocol can belong
to one study, and a study can contain several protocol documents. Names are
not used to group documents automatically.

## Workflow

1. Open **Studies → All studies** and select **Create study**. Enter the
   agreed study name and ID. IDs are case-insensitive within a sponsor and
   stored in uppercase; different studies can share a display name.
2. Open **Upload Protocol** from the sidebar. Search for and select a study,
   or create one from this page. Choose a PDF or load the synthetic sample.
3. Open a study to see its protocols and their existing review, data and
   report links. Study pages have no upload controls.
4. Existing documents remain **Unassigned** after upgrading. Use
   **Studies → All protocols → Unassigned**, select a study on each protocol,
   then choose **Save assignment**. The same control can explicitly move a
   protocol to another study or return it to Unassigned.

Assignments do not change protocol IDs, extracted forms, review history,
site assignments, patients or observations. Protocol amendments can be
separate documents in the same study; this feature does not automatically
classify amendments or migrate clinical data between documents.

Re-uploading identical document text reuses its existing protocol. Uploads
cannot silently move a document that already belongs to another study:
change the assignment explicitly from All protocols instead. Distinct
documents with the same upload filename are stored separately.

## Compatibility and access

Study management is sponsor-only and scoped to the signed-in sponsor's
organisation. The existing site portal and its locked-protocol access
rules are unchanged. New management endpoints are under
`/api/sponsor/studies`, separate from the existing site-facing `/api/studies`.

The upload screen requires study selection. Existing API clients can still
omit `study_id`, leaving their uploads unassigned for later manual review.

Migration `0010` adds study and assignment tables without rebuilding or
deleting existing protocol or clinical tables. `bash run.sh` applies it
automatically; with an existing virtual environment, it can also be run
from `ecrf-prototype/backend`:

```bash
.venv/bin/alembic upgrade head
```

## Checks

```bash
cd ecrf-prototype/backend
.venv/bin/python -m pytest tests/test_study_management.py -q
.venv/bin/ruff check .
```

Frontend validation, from `ecrf-prototype/frontend`:

```bash
npm run build
npm run lint
```
