# eCRF Status

Sponsor users open **eCRF Status** at `/sponsor/ecrf-status` from the sidebar.
The protocol Sites page links here with its protocol preselected. This is
a read-only view of **hospital-side registrations and saved visit entries**,
not sponsor review, query management or clinical analytics.

## Hospital-first layout

Each hospital appears once. Expand its card to see its protocols, grouped
under their study labels, and then patient codes and visit updates.
Search and filters for study, protocol, hospital and entry status remain.
Patient-code search narrows patient details as well as the hospital list.
Filtered summary cards show hospitals, currently assigned locked protocol
forms, hospital patient registrations and patients with at least one saved
visit entry. Patients are counted separately per protocol; no cross-study
identity matching is attempted.

Assigned eCRFs means existing protocol/site assignments with a locked form,
not confirmed email delivery or acknowledgment. Historical hospital
registrations/entries remain visible after unassignment, clearly labelled
**No longer assigned**. Nothing is dispatched by opening this page.

## Simple update states

- **Awaiting patients:** no hospital patient registration or entry yet.
- **No entries yet:** patients are registered, but no nonblank visit values
  have been saved by that hospital.
- **Hospital entries received:** at least one patient has a saved entry.
  This is not a completed/submitted/approved form designation.
- Each patient's visit list shows **Entries saved** or **No entries yet**,
  with the last hospital entry/change date where available.
- **Latest visit updated** identifies the visit most recently edited by
  the hospital, not the furthest week in the protocol or a confirmed
  current study week. Backfilling Screening after Week 4 shows Screening
  as the latest update. Tied visits are listed together.
- No completion percentages, required-field/repeat totals, approval counts,
  query counts, schedule scores, on-time or overdue labels are shown.
  Schedule tracking is deferred until the client confirms the rules.

Visit names come from the approved fields in the current locked eCRF.
Visits with no entries can be future visits: they are not labelled missed
or overdue. A zero or explicit No is still a saved value. Blank/whitespace
values do not make a visit have entries, but a hospital clearing a value is
still a hospital update.

## Hospital-side activity only

`GET /api/sponsor/ecrf-status` requires `stats.view` and scopes all source
protocols, patients, observations and change histories to the sponsor.
It returns hospitals with nested protocol and patient visit updates.

Hospital registration authors and observation entry/change authors are
matched to that site's user accounts. Last-update dates use the hospital's
registration, original entry and value-change history timestamps.
Sponsor approvals, query activity, assignments and form configuration do
not advance these dates or change entry statuses. Correcting a value
through a query does count because it creates a hospital-authored value
change. System-seeded records are not passed off as hospital activity.

Readings must match the registered patient, protocol, current locked eCRF
version and a field/repeat on that form. Legacy unlinked or older-version
readings are not presented as current hospital updates. No patient names,
initials, birth years or actual clinical values are returned here.

The page loads on opening and refreshes manually, with a visible refreshed
time. It does not poll, seed records, call a model or change assignments.
Existing review and query pages retain their full functionality. No new
dependency or migration is needed.

## Validation

Backend: `pytest tests/test_ecrf_status.py -q` and `ruff check .`.
Frontend: `npm run build` and `npm run lint`.
