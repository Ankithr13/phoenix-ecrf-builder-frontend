# Sprint 3 progress

Stage 1. Fixes from the audit: done
Stage 2. Put it online: skipped (by Tarushi, to test locally first; all of its work was removed)
Stage 3. Roles, admin panel, approval chain: todo
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
