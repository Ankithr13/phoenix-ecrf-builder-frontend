# Review workflow

One protocol has one review page at `/sponsor/p/:id/review`. Successful field
extraction already opens this page. Studies and eCRF Management link to the
same saved form; they do not create separate copies or separate review tabs.

## Finding unfinished work

eCRF Management groups protocols by study, with search and study/stage
filters: All, Not extracted, Needs review / finalization and Locked.
Drafts remain in Needs review / finalization until explicitly locked.
`?pending=1` links from the existing dashboard still select this category.
Filter selection is stored in the URL. Counts on the stage buttons cover
the workspace, not only the selected study/search.

Cards show saved version and the actual current draft/flagged decision
counts from the backend's lock checks, not the original extraction summary.
Drafts with remaining decisions say **Draft — review incomplete**; drafts
with no remaining decisions say **Draft — ready to finalize**. Actions open
extraction, Continue review, Review & finalize or View locked form as
appropriate. Study pages provide the same review links. There are still no
study-page upload controls and no separate "under review" workflow state.

## Saving versus approval

Review has Save draft and Save draft & exit. The latter returns to unfinished
forms in eCRF Management. A review note can be saved without field edits.
Saving uses the existing append-only review-version endpoint. It preserves
explicit field decisions but never approves remaining fields, locks a form
or assigns hospitals automatically. Applied edits are unsaved until saving
succeeds. Success is shown only after the save response; if reading back the
saved form fails, editing/finalization pauses and offers Retry loading.
Failed save requests keep applied edits and notes on the page.

An open field editor must be Applied or Cancelled before saving, filtering
or changing visits. This prevents silently losing typed, unapplied values.
The review progress counts reflect applied local changes across all visits;
locking checks the saved version. Original extraction diagnostics remain
available in expandable Extraction details and Verification results sections.

Bulk library/guessed-range acceptance and approval of remaining draft fields
require explicit confirmation and identify their scope as all visits, not
only the visible filter. Existing backend approval rules are unchanged.
Flagged fields are not silently included in "Approve remaining draft fields".

## Leaving, discarding and locking

Internal navigation, browser back and Sign out offer Stay, Save draft & leave
or Discard changes & leave when there is unsaved work. With an open field
editor, stay and Apply/Cancel first before saving, or explicitly discard its
unapplied edits. During saving/locking, leaving is blocked until the request
finishes. Refresh, closing the tab and external navigation use the browser's
native unsaved-work warning rather than a custom three-choice dialog.
Browsers control when these native warnings are shown.

Discard unsaved changes requires confirmation. It resets only edits since
the last successful save, including open field editors. It does not remove
the uploaded protocol, saved versions, study or clinical data. No local
browser storage or automatic background saving is introduced.

Finalize & lock is disabled until all saved fields have decisions and local
work is saved. Confirmation names the protocol and saved version and explains
that locking freezes editing. Existing lock warnings and server-side blockers
remain authoritative. Hospital assignment is still separate in Sites; locking
does not declare hospital data complete. Locked forms are read-only.

The router now uses the installed React Router data-router wrapper so its
supported navigation blocker can protect review routes. URL paths and the
existing authentication/role guards remain unchanged.

## Validation

Backend tests cover resumable edits without automatic approval, note-only
drafts, actual management decision counts, explicit locking and unchanged
hospital access. Run `pytest tests/test_review_workflow.py` plus the existing
review/lock/site and broader regression tests. Frontend build/lint and browser
checks cover routes, filters, editor handling and unsaved-navigation choices.
Browser verification should discard temporary edits, not save or lock live
client records just for testing.
