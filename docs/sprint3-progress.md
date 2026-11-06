# Sprint 3 progress

Stage 1. Fixes from the audit: done
Stage 2. Put it online: skipped (by Tarushi, to test locally first; all of its work was removed)
Stage 3. Roles, admin panel, approval chain: done
Stage 4. Foundation form, field comments, form audit trail: todo
Stage 5. Data entry rules and edit checks: todo
Stage 6. Query lifecycle, notifications, investigator sign-off: todo
Stage 7. Dashboard metrics, SAP mapping, biostatistics, PDF: todo
Stage 8. Documentation and the regression run: todo

Client documents: `docs/client/` is not present, so the summaries inside SPRINT3.md are the source.
Starting test count: 143.

## Stage 1 acceptance

Tests: 159 passed, was 143.

1. Upload path traversal: done. `test_upload_filename_cannot_escape_upload_folder`
2. Upload overwrite: done. `test_upload_with_same_name_does_not_replace_stored_pdf`
3. Site cannot withdraw approval: done. `test_site_cannot_close_a_query`, `test_approved_value_edit_needs_open_sponsor_query`
4. Query corrections follow entry rules: done. `test_query_correction_uses_entry_validation`, `test_query_correction_recomputes_derived_value`. One function, `save_readings` in `api/data.py`
5. No green pass on an unavailable stat: done. `test_null_stat_is_not_available_not_pass`, `test_null_stat_on_the_dashboard_is_grey`
6. Seed button: done. `test_seed_refuses_without_locked_form`, `test_seed_handles_subject_with_no_readings`
7. Unassigning a site with data: done. `test_unassign_site_with_data_needs_force`, warning in `pages/Sites.tsx`
8. Forced re-extraction refreshes the cache: done. `test_forced_reextraction_refreshes_cache`
9. Re-extraction guard: done. `test_reextraction_is_refused_after_review_unless_forced` asserts `replaced_draft`, confirm in `pages/Visits.tsx`
10. `unsupported` route: done. `test_unsupported_route_is_scoped_and_404s`
11. Dead code: done. `api.extract`, `api.history`, `.column_descriptions` and `section_ok` removed; `GET /api/data/{id}/subjects` kept
12. Deployment defaults: done. `test_prod_refuses_default_secret`, `scripts/seed_demo.py`. SECRET_KEY now keys the session token hash, so it does real work
13. Initials: done. `test_subject_has_no_initials`, migration `0010_audit_fixes.py`
14. Price config: done. `test_cost_not_configured_when_prices_missing`, `format.ts` `costText`
15. Stale docs: done. `CLAUDE.md`, `ecrf-prototype/README.md`

Choices to confirm:

- The sprint rule says patients are identified by server-generated codes, so typed subject IDs are gone too, not only initials. The registration body now refuses unknown keys.
- The status `entered` became `submitted` here, not in Stage 5, because item 6 needs `submitted` now.
- A real `.env` using the old `PRICE_*` names now shows "cost not configured" until renamed to `LLM_PRICE_*`.

## Stage 2

Skipped on request. The Dockerfile, Railway config, deploy notes, frontend serving, `PORT` and `CORS_ORIGINS` settings, health changes, Postgres test and the verifier's move to SQLAlchemy were all removed before being committed. Stage 1's `ECRF_ENV` and `SECRET_KEY` handling stays, because it is committed Stage 1 work.

For when this comes back: running the migrations on real Postgres 16 found that a `%` in `DATABASE_URL`, such as a URL-encoded password, crashes `migrate.alembic_config` through configparser interpolation. The fix is to double the `%` before `set_main_option`.

## Stage 3 acceptance

Tests: 203 passed, was 159 at Stage 1 (Stage 2 tests were removed with the stage).

1. Roles: done. `ecrf/auth/permissions.py`, `test_matrix` asserts every cell, `test_old_roles_migrate_to_new_roles`, migration `0011_eight_roles.py`
2. Users and `user_access_event`: done. `test_admin_creates_user_and_access_event_is_written`, `test_admin_edits_role_and_monitor_sites`
3. Admin panel: done. `frontend/src/pages/Admin.tsx`, `ecrf/api/admin.py`, `test_deactivated_user_cannot_log_in`, `test_approval_chain_switches`
4. First login: done. `test_must_change_password_blocks_other_routes`, `pages/ChangePassword.tsx`, redirect in `App.tsx` `RequireAuth`
5. Protocol chain config: done. `test_approval_chain_switches`. Enforced in Stages 5 and 6
6. Portals: done. `components/Layout.tsx` filters by permission. Browser check as `auditor@phoenix.demo`: Review shows no Approve, Reject, Flag, Edit, Lock or Save button
7. Demo accounts: done. `ecrf/auth/demo.py`, listed on the login page only under `import.meta.env.DEV`
8. Glossary and instructions: done. `pages/Glossary.tsx` Roles section, `instructions.md`
9. Other tests named in the stage: done. `test_monitor_sees_only_assigned_sites`, `test_read_only_has_no_write_route`, `test_site_data_entry_cannot_create_subject`, `test_builder_cannot_lock_and_dm_cannot_edit_form`
10. Route walk: done. `test_every_router_route_declares_a_permission`. Every router route uses `require(perm)` except login and logout; `/me` and change-password need a signed-in user and nothing more. Health is on the app itself and open

Browser check on a throwaway database: admin lands on `/admin`; a new user sees the temporary password once; signing in with it lands on `/change-password` and nothing else opens until it is changed.

Choices to confirm:

- The matrix gives sponsor roles no `query.answer`, but queries run both ways, so a site's question would have no one to reply. Whoever holds `query.close` may reply in words to a query a site raised.
- The matrix has no permission for reading entered values row by row. `DATA_READERS` is `listing.view`, `data.enter` or `data.approve`, so the admin, builder and read-only roles see totals only.
- Seeding, which is not in the matrix, needs `data.approve`.
- The `unsupported` demonstration route needs `sap.edit`, so `read_only` gets 403 on every non-GET route as `test_read_only_has_no_write_route` requires.
- The stage says the login page lists demo accounts in dev only. That brings back the list removed for the midterm video, so a recording made under `npm run dev` will show it.
- Until Stage 7, site and monitor roles see scoped totals on the dashboard and no statistics, because the statistics describe the whole study.
