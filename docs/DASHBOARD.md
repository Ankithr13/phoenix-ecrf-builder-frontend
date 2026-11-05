# Sponsor workspace dashboard

The sponsor home at `/sponsor` is a workspace overview. The study list is
at `/sponsor/studies`; study detail and protocol-level report URLs retain
their existing routes. Site staff continue to land in the site portal.

## Metrics

All counts come from the signed-in sponsor's records through
`GET /api/sponsor/dashboard`. No sample numbers or inferred clinical
activity states are displayed.

- **Total studies:** study records owned by the sponsor.
- **Protocol documents:** distinct protocol records, including unassigned
  documents. Repeated uploads of identical text remain one protocol.
- **Pending eCRF reviews:** protocols whose latest eCRF version is a draft.
  This includes forms whose field decisions are complete but which have
  not yet been locked. The card opens the matching pending-review list.
- **Queries needing you:** open queries raised by the other organisation
  type, plus answered queries raised by the sponsor and awaiting closure.
  The dashboard shares this rule with the query inbox.

Form progress is derived from each protocol's latest version. Earlier
draft or locked versions do not contribute to the counts. Unassigned
protocols contribute to workspace totals and get an assignment reminder,
but do not appear under a study until assigned manually.

## Study table

The table supports a name/ID search and filters for review, extraction,
and locked-form progress. The status priority for a study with mixed
protocols is:

1. Needs review: one or more latest forms are draft.
2. Needs extraction: one or more protocols have no extracted form yet.
3. Forms locked: all protocols have locked latest forms.
4. No protocols: the study has no assigned documents.

These describe protocol form progress, not recruitment or clinical study
activation. The update date reflects protocol uploads, manual study
assignments, and the creation or locking of the latest eCRF version. New
studies and recent protocol updates sort first.

The overview loads when opened and can be refreshed with the refresh
button. It does not poll or make model calls. Create new study opens the
existing study form; View study opens the existing protocol list. Uploads
remain in the standalone Upload Protocol page.

## Validation

From `ecrf-prototype/backend`:

```bash
.venv/bin/python -m pytest tests/test_workspace_dashboard.py tests/test_queries.py -q
.venv/bin/ruff check .
```

From `ecrf-prototype/frontend`:

```bash
npm run build
npm run lint
```
