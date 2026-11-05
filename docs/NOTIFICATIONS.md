# Hospital notifications and entire-eCRF submissions

This feature is in-app only. It sends no email, SMS, desktop/browser push
or external service messages. Existing Phoenix branding is unchanged.

## Client/sponsor workflow

- The bell next to the sidebar logo shows the signed-in user's unread count.
- It opens `/sponsor/notifications`, with all/unread filtering, personal
  read receipts, refresh, individual/mark-all read controls and pagination.
- New hospital-raised queries create **New hospital query** alerts. Opening
  one goes straight to that query, even if it has since been answered or
  closed. Sponsor-raised queries and ordinary saves do not create alerts.
- Explicit hospital submissions create **Hospital submitted eCRF** alerts.
  Opening one filters eCRF Status to the correct hospital/protocol and opens
  the hospital card. The status page distinguishes a current submission
  from subsequent changes.
- The bell checks on opening/navigation, focus, returning to a visible tab,
  and about every 30 seconds while visible. This is polling, not instant
  push. Failed refreshes are indicated rather than displaying a false zero.
- Notifications and personal read receipts persist across reloads/logins.
  Reading an alert does not read it for other sponsor team members or
  change a query, eCRF, patient or clinical value.

Alerts are generated for new actions after this feature is installed.
Historical queries remain in Queries, but are not backfilled into alerts.
Query replies are still handled by the existing Queries attention badge;
they do not generate additional notification events in this version.

## Hospital completion is an explicit declaration

The hospital's Patients page for an assigned protocol contains **Submit
your hospital's entire eCRF**. The staff member confirms that all of their
hospital's work for that assigned eCRF is ready for sponsor review and
clicks **Submit entire eCRF for review**.

This covers **that hospital × one assigned protocol**, across all its
registered patients and visits. It does not submit another hospital's
data, another protocol in the same study, or just the currently open
patient/visit. The form must be locked and assigned to the site, with
registered patients and at least one nonblank saved entry against that
locked version. An empty or unassigned eCRF cannot be submitted.

Completion is the hospital's declaration, not a calculated percentage or
an automatic check that every required field/visit is finished. No due
dates, on-time/overdue judgments or sponsor approval are inferred. Until
the client confirms completion rules, staff are responsible for deciding
whether all expected work is ready. Submission does not approve, sign or
freeze clinical data; existing data-review/query protections still apply.

Each submission records the submitter, UTC time, locked version, patient
count and a hash of the site's patient/entry content. Changing that content
or adding patients makes the state **Changed since submission**. Staff
must review and submit the new content to send a new alert. Another site's
changes, sponsor approvals and query-state changes do not invalidate it;
a hospital correcting an actual value does. Duplicate clicks on identical
content reuse the existing submission and never generate duplicate alerts.
Reverting to an identical previously submitted snapshot also reuses that
prior declaration. The submission history is append-only.

The hash is not a clinical-data archive or a replacement for existing
observation/version history. Notifications contain hospital and protocol
context, not patient demographics, clinical values or question text.

## API and storage

- `GET /api/notifications`: sponsor-scoped paginated events, personal read
  state and total unread count; accepts `before_id`, `limit` (1–50), and
  `unread_only`.
- `POST /api/notifications/:id/read`: idempotent personal read receipt.
- `POST /api/notifications/read-all`: personal receipts through the
  displayed `through_id`; events arriving later are not silently read.
- `GET /api/studies/:protocolId/submission`: the assigned site's state.
- `POST /api/studies/:protocolId/submission`: requires `confirmed: true`.

New permissions: sponsor `notifications.view`; site `ecrf.submit`.
Read and submission routes enforce role and organisation/assignment scope.
Queries and their events are committed together; so are submissions and
their events. Unique event/snapshot constraints guard duplicate writes.

Migration `0011` adds `hospital_submission`, `notification` and
`notification_read`. Existing clinical tables are not rebuilt or changed.
Normal `bash run.sh` applies it. When updating an already running backend,
apply `.venv/bin/alembic upgrade head` from `ecrf-prototype/backend` before
using the new endpoints. A local SQLite backup was made under the ignored
backend `.venv` directory before applying the development migration.
No new dependency was added.

## Validation

Backend: `pytest tests/test_notifications.py tests/test_queries.py tests/test_ecrf_status.py -q`
and `ruff check .`. Tests use temporary databases, not the local demo.
Frontend: `npm run build` and `npm run lint`.
