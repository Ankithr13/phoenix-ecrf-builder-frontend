# Updated frontend feature branches

These branches preserve the updated prototype at `29dd2be`, with its eight
roles and patient-visit submissions. Earlier feature branches are retained.
No official repository branch or existing fork branch is overwritten.

| Branch | Compare / PR base | Contents |
| --- | --- | --- |
| `base/prototype-29dd2be` | Exact upstream snapshot | Existing updated prototype; no new UI changes. |
| `feature/navigation-ui-v2` | `base/prototype-29dd2be` | Original logo/theme, sidebar, breadcrumbs, permission-safe empty previews, shared protocol chooser and frontend helpers. |
| `feature/dashboard-ui-v2` | `feature/navigation-ui-v2` | Study overview, four metrics, recent-studies layout and connected protocol/query counts. |
| `feature/study-workspace-ui-v2` | `feature/navigation-ui-v2` | Empty study workspace and disabled study-creation form. Real grouping needs backend support. |
| `feature/protocol-upload-ui-v2` | `feature/navigation-ui-v2` | Local PDF preview/confirmation, upload/error flow and disabled study-assignment placeholder. |
| `feature/ecrf-review-ui-v2` | `feature/navigation-ui-v2` | Resumable draft review, unsaved-change guards and comments/editor protection with upstream field functionality. |
| `feature/ecrf-status-ui-v2` | `feature/navigation-ui-v2` | Hospital-grouped progress, filters, patient visit-stage counts and empty previews for restricted roles. |
| `feature/notifications-ui-v2` | `feature/navigation-ui-v2` | Original notification cards, unread/kind/protocol filters and show-more connected to current alerts. |
| `integration/frontend-ui-v2` | Combined preview | Local merges of the foundation and all six feature branches. Use this to run the complete UI. |

## Review and merge order

Review navigation first. Each of the six feature branches then adds only its
own changes relative to that shared foundation; they do not contain one
another's feature commits. A small entry file per feature avoids each feature
editing the shared router or importing another unfinished feature.

Compare each branch against the base listed above. Comparing to the fork's
older `main` also includes the upstream prototype changes, making the UI
diff misleadingly large.

The combined branch is for testing the whole UI, not six separate feature PRs.
No pull requests are opened or merged automatically. When the official
`dev` contains the agreed prototype and navigation foundation, adapt the
feature PR bases to that branch and check the diff again.

## Making the next change

For a feature whose PR is still open, switch to its `-v2` branch, edit,
test and commit. Pushing that branch updates that feature's PR.
After its PR is merged, start a new branch from the current official
development base for the next improvement.

Changes to shared navigation belong on the navigation branch. Update the
other branches deliberately after reviewing that shared change; avoid
copying the combined preview into every feature branch.

The study placeholders contain no sample records. Database files, uploads,
dependencies, build outputs and local test helpers are excluded.
