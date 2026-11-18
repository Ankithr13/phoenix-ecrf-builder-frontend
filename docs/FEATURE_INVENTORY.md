# Frontend feature inventory

Reference: the original study dashboard screenshot supplied on 16 November.
Integration branch: `feature/ui-upstream-integration`, based on upstream
`29dd2be`. The updated prototype's eight roles, APIs, patient-visit submission
workflow and backend remain unchanged.

The sponsor workspace retains the complete original navigation. Visibility
does not grant access: links that a role cannot use open empty layout
previews without requesting protected records.
Site navigation and selected-protocol tools remain permission-filtered.

| Feature | Current behavior |
| --- | --- |
| Original Phoenix logo, teal sidebar, compact identity footer | Restored. No research / BU Spark card. Account utilities remain under the name menu. |
| Dashboard, Studies, Upload Protocol, eCRF Management, eCRF Status, Clinical Data Review, Analytics & Reports, Queries | All sponsor destinations remain visible. Studies expands into All studies and All protocols. |
| Study overview dashboard | Original four metric labels, date, create-study action, recent-studies panel, tabs, table columns and footer composition. |
| Total studies | Unavailable dash, not zero. Study grouping has no backend endpoint yet. |
| Protocol documents / Pending eCRF reviews | Counts use the existing scoped protocol list and template states. No fake study grouping. |
| Queries needing you | Real actionable count for authorized query roles; unavailable for other roles or on request failure. No forbidden query request. |
| Recent studies / All studies | Original table/card workspace composition with an explicit empty state, no sample names, IDs or invented counts. Study search and filters cannot return unavailable records. |
| Create new study | Opens a disabled empty form showing study name and ID. No save, assignment, API call or browser-storage record. |
| Protocol grouping / assignment to studies | Backend work remains pending. Actual protocol documents stay available separately under All protocols. |
| Standalone upload | Original choose-study/file/confirm structure restored. Study selection is visibly disabled until connected and does not block uploading via the existing API. No sample button and no upload controls inside Studies. Other roles see a disabled preview. |
| eCRF Management | Live protocol search, stage filters and links to the existing shared review page. |
| Shared review page | Save draft, save-and-exit, discard and leave warnings; upstream field editing, foundation fields, comments/history, CDASH, ranges and missing-value options retained. |
| Template finalization / hospital assignment | Existing permissions and server blockers remain authoritative. No new grants. |
| eCRF Status | Original metric/filter/hospital-card presentation with live current API data for permitted roles. Restricted roles get the same presentation with empty placeholders and no status/protocol requests. Visit names and edit timestamps remain unavailable. |
| Clinical Data Review | Authorized reviewers use the existing submitted-answer workflow. Other roles see an empty preview and cannot read patient values. |
| Queries | Existing query actions for authorized roles; empty preview for restricted roles. |
| Notifications | Original cards, unread-only filtering and show-more presentation with upstream alert types, kind/protocol filters, personal read actions and unread bell. Admin has no inbox. Additional rows are revealed locally from current API results. |
| Analytics, reports, listing, results/SAP, PDF | Existing upstream functions and permissions retained. Blank-template PDF remains distinct from patient-value exports. |
| Admin, change password, glossary | Upstream features retained. Admin remains permission-gated. |

The study previews are intentionally empty, as requested. Existing connected
protocol screens still display the records returned by their current APIs;
they do not present those records as invented studies.

## Remaining work

1. Remaining browser checks: PDF selection/preview/upload, draft save and leave guards,
   read actions and a fuller audit of all eight roles.
2. Connect study creation, grouping, assignments and study-level counts to real APIs.
3. Refine role-specific page priorities using this shared shell.
4. Confirm hospital timelines and schedule rules with the client before adding them.

This pass does not claim a complete redesign of every page for all eight roles.
Backend code, migrations, API types/client and dependency manifests are unchanged.
No commit, push or merge is part of this local restoration.
