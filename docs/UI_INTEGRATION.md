# UI integration with the updated prototype

Branch: `feature/ui-upstream-integration`.
Base: upstream `main` at `29dd2be64a517e80e8a215722e348e424f4e0099`.
Earlier UI source: `feature/review-workflow` ending at `7075fe9`.

This is a selective frontend integration. The upstream backend, migrations,
API contracts, eight-role permissions, approval-chain settings and patient-visit
submissions are retained. The original checkout and database are untouched.

## Included

- Original Phoenix logo, full sponsor sidebar, responsive menu, breadcrumbs,
  search/refresh header and compact profile/sign-out footer.
- Studies expanded into All studies and All protocols.
- Study overview with the reference's four metric labels and recent-studies
  table columns, filter tabs, create-study action and footer.
- Empty, clearly labelled placeholders for study grouping, study counts and
  creation. No sample study records, invented counts or browser-only grouping.
  Creation fields and save are disabled until actual backend support is added.
- Real scoped protocol/review counts and authorized actionable query counts.
  Unsupported or inaccessible values display a dash, not a false zero.
- All sponsor menu destinations remain visible. A permission-aware wrapper
  renders an empty layout preview for restricted sections without fetching
  protected records. Upload and status reuse their restored presentation in
  preview mode; status requests are disabled. Backend authorization stays intact.
- Standalone PDF selection, local preview and explicit upload confirmation.
  No client-facing sample-protocol action or automatic upload on selection.
- Live All protocols / eCRF Management with stage/search filters and shared review.
- Save draft, save-and-exit, discard confirmation and leave guards, integrated
  with upstream comments/history, foundation fields, CDASH, reference ranges,
  collection flags and missing-value options.
- Unposted comments, open editors and in-flight comment saves are protected
  from silent navigation, filtering and visit changes.
- Existing template finalization confirmation and server blockers.
- Hospital-grouped eCRF Status using existing Page status data for permitted
  roles, with protocol/hospital/patient/status filters and submitted-answer links.
- Original notification cards, unread-only control and show-more interaction,
  connected to upstream notification types, kind/protocol filters, personal read
  actions and unread bell. Show more reveals already fetched records in batches;
  it does not invent a pagination endpoint.

## Original source restoration

The 18 November pass restores the dashboard source and workspace stylesheet
from `feature/review-workflow` at `7075fe9`, rather than approximating the
reference. Dashboard data now lives in a separate frontend hook using current
protocol/query APIs. The original card sizing and link-based create action
are retained. New placeholder styles live separately in `workspace-adapters.css`.

The original upload structure, study creation presentation and hospital-progress
styles/cards are reused. Study assignment is disabled and does not block the
current standalone upload API. Hospital visit-stage counts come from the
current API; unavailable visit names/update timestamps remain dashes.

Signed visits also count as approved under the current API. No percentages,
schedule judgments, guessed current week or whole-hospital submission flow
have been introduced. The older notification backend and migration revisions
0010/0011 are not copied, avoiding conflicting database histories.

See `FEATURE_INVENTORY.md` for connected features, placeholders and remaining work.

## Isolated local preview

Preview: `http://127.0.0.1:5174`, backend: `127.0.0.1:8001`.
The original app on 5173/8000 is unchanged. Use 127.0.0.1 rather than localhost
for this preview to avoid sharing the original app's session cookie.

Existing upstream demo accounts use password `demo1234`:

- `builder@phoenix.demo`: protocol upload and template editing.
- `dm@phoenix.demo`: permitted clinical review, progress, reports and template lock.
- `admin@phoenix.demo`: administration, without clinical-value or inbox access.
- Other upstream demo accounts remain available unchanged.

The ignored `.venv/ui-integration/preview.db` contains the pre-existing isolated
upstream synthetic walkthrough (16 patients), not client records. That data is
used only by connected screens; unconnected study previews contain no records.

Restart in two terminals from this worktree. Backend:

```sh
cd ecrf-prototype/backend
DATABASE_URL="sqlite:///$PWD/.venv/ui-integration/preview.db" \
ECRF_UPLOAD_DIR="$PWD/.venv/ui-integration/uploads" ECRF_BACKEND=mock \
.venv/bin/python -m uvicorn ecrf.api.app:app --host 127.0.0.1 --port 8001
```

Frontend:

```sh
cd ecrf-prototype/frontend
ECRF_API_TARGET=http://127.0.0.1:8001 npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

The optional development proxy target leaves the default backend address
unchanged when unset. Ctrl+C stops each preview server.

## Verification

Frontend build and lint, server-rendered navigation/placeholder checks and
read-only runtime/API checks cover this integration. The unchanged upstream
backend suite previously passed 330 tests with one skipped. The isolated
walkthrough checked entry, visit submission, queries, approval, sign-off and
PDF output on a database copy.

Runtime checks covered all eight role sign-ins, denied Admin/Builder
clinical-value access, Admin inbox denial, submitted-only sponsor data,
Page status and the frontend proxy.

The 18 November browser pass checked Builder and Data manager sign-in, full
navigation, original dashboard layout, Builder's empty status preview, upload
controls, disabled study creation/cancel, management-to-locked-review navigation,
live hospital grouping/search/expansion, notification kinds/filtering and
show-more (25 to 50 alerts). Mobile navigation at 390px opened correctly without
page-wide horizontal overflow. The temporary viewport override was reset.

This is not a claim of an exact pixel match or a full eight-role interaction
audit. Upload file preview/submission, draft save/discard/leave dialogs and
notification read mutations were not exercised in this browser pass.

Dependency manifests were not upgraded. Existing dependency advisories and
the Node-engine warning remain outside this UI change.

Nothing has been committed, pushed, merged or published.
