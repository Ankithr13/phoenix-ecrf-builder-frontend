# Protocol upload review

Protocol uploads remain a separate workspace page at `/sponsor/upload`.
Study pages do not gain upload controls. Study assignment is manual.

## Review and confirm

1. Choose an existing study by name/ID, or explicitly create a study.
2. Choose a `.pdf` file. Empty files and non-PDF filenames are rejected
   locally. This selection does not send the document to the server.
3. Review the study ID/name, filename, file size and browser PDF preview.
4. Select **Confirm and upload protocol** to send it to that study.

The preview uses a local object URL, revoked on replacement, cancellation,
success or unmount. The browser's native PDF viewer is used, with a link
to open the selected local PDF separately when embedded preview is unavailable.
Preview is not validation: the backend still checks and parses the document.
The existing backend has no configured size limit; no arbitrary frontend
limit has been added. Text-based PDFs are required; OCR is not implemented.

Changing study updates the review summary without uploading. Cancel
selection discards the pending file without writing a protocol. There is no
sample-protocol option on this client-facing page: users select their own PDF.
Creating a study remains an explicit separate save, not an upload preview.

## Failures and duplicates

Loading studies can be retried; uploading is disabled while the list is
loading or unavailable. The list can also be refreshed without losing a
selected file. A study removed from the refreshed list must be reselected.

Upload failures retain the selected document and study for correction or
explicit retry. Messages cover permissions/session issues, unavailable
studies, invalid/scanned files, server file-size rejection and conflicting
study assignments. Unconfirmed network/server results tell staff to check
All protocols before retrying: a lost response does not prove a failed save.
An in-flight guard prevents repeated clicks starting concurrent requests.

Existing server-side normalized-text deduplication is unchanged. Repeated
uploads reuse an existing protocol; a protocol already belonging to another
study is not silently moved. Successful results keep the existing links to
extraction and the study's protocol list. Upload does not start extraction.

Selections are in memory only and are lost when leaving/reloading the page.
There is no background upload, local persistence, new dependency, schema
change, automatic study detection or change to clinical records.

## Validation

Run the existing frontend build/lint and backend study-management tests.
Browser checks should verify selection/review/cancellation without creating
live records; server upload/deduplication tests use an isolated test database.
