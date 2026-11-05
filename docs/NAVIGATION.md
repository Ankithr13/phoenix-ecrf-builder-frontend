# Study and protocol navigation context

The original Phoenix logo, notification bell and role-specific workspace
links remain. Navigation now distinguishes global workspace destinations
from tools belonging to one selected protocol.

## Workspace versus protocol tools

Workspace links always have stable destinations. eCRF Management opens
the workspace's protocol chooser, Clinical Data Review opens its chooser,
and Analytics & Reports opens its chooser. These links no longer silently
switch to a particular protocol when another page happens to be open.

Opening a protocol shows a **Selected protocol** card with its actual study
name/ID, protocol name and draft/locked/not-extracted state. A separate
**Protocol tools** group contains Visits & extraction, eCRF Review, Sites,
Data review and Reports for that protocol. Back to study returns to its
study's protocol list; All studies allows changing study. Unassigned
protocols are identified explicitly and link back to All protocols.

Opening a study without a protocol shows its study context and a prompt to
open a protocol for its tools. On hospital pages, **Assigned eCRF** shows
the authorized study/protocol and patient code where applicable, with
Patients and Change study navigation. No patient demographics are shown.
Protocol tools appear only after their context loads successfully.

The selected context comes from the current URL, not a remembered last
selection. Global pages and filtered status views do not inherit a stale
protocol. Switching study/protocol/account clears the rendered old context
immediately; late responses are ignored. Failed detail loads provide Retry
details while preserving global navigation. Context is refreshed when
entering a protocol again after leaving its workspace, on reload, or by
retrying; it is not a live cross-browser assignment subscription.

## Shared breadcrumbs and accessibility

One shared header provides breadcrumbs on all signed-in pages. Study names
link back to the study when the sponsor is authorized; the last breadcrumb
has `aria-current="page"`. Patient entry pages link back to Patients.
Names wrap for narrow screens rather than losing their full labels.

Existing dashboard search/refresh and status/notification refresh controls
share this same header, without a second breadcrumb bar. Page controls are
rendered into the header by a React portal and removed when their page
unmounts; the underlying pages and actions are unchanged.

The main menu highlights its actual destination. Protocol links no longer
appear as generic Visits/Sites inside the global Studies folder. On mobile,
the menu closes after navigation and Escape closes it and returns focus to
the menu toggle. Changing study/protocol scrolls the sidebar's navigation
area to the top so the new context is visible; it does not scroll forms.

## Read-only context API

`GET /api/navigation/protocols/:protocolId` returns only protocol ID/name/
state, its authorized study ID/name/code and an optional patient code.
`subject` may be supplied on patient entry routes. The endpoint uses existing
protocol assignment/organisation and subject scope rules: hospital users
need a locked, assigned protocol and can only request their own patient.
Unassigned or unauthorized protocols/patients return 404. Other sponsors'
study metadata is not exposed even if an imported assignment is inconsistent.
It performs no extraction, data changes, migrations or new permission grants.

Study-only pages use the existing sponsor-scoped study lookup. No browser
storage, dependencies, upload controls on study pages, or new clinical
workflow states have been introduced.

## Validation

Backend: `pytest tests/test_navigation.py -q` and `ruff check .`.
Frontend: `npm run build` and `npm run lint`.
Browser checks cover study/protocol transitions, shared header controls,
global versus protocol links, and unavailable context.
