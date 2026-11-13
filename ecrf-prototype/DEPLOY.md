# Hosting on Vercel with Supabase

Vercel serves the frontend and runs the FastAPI backend as one Python
function (`api/index.py`). The database is Supabase Postgres. Moving to Railway
later means a different host for the same code and a `DATABASE_URL` change.

Run the npm commands from `ecrf-prototype/frontend`.

## Once

1. **Supabase.** Create a project and note the database password. Then go to
   Connect, choose "Transaction pooler", and copy the URI on port 6543.
2. **Settings file.** Run `npm run vercel:env` to create
   `ecrf-prototype/.env.vercel.local` from `.env.vercel.example`, then fill in
   `DATABASE_URL`, `SECRET_KEY`, `LLM_API_KEY` and `DEMO_PASSWORD`. The file is
   git-ignored and never uploaded.
3. **Database.** Run `npm run db:setup`. It runs the migrations on Supabase
   and loads the demo story (16 synthetic patients and the ten demo accounts,
   using `DEMO_PASSWORD`). It refuses to run if the database already has users.
   Run `scripts/load_postgres.py --help` to see the other modes: accounts only,
   migrations only, and `--replace`.
4. **Vercel project.** Run `npm run vercel:login`, then `npm run vercel:link`.
   Link `ecrf-prototype` as the project's root directory.
5. **Environment variables.** In Vercel, go to Settings, then Environment
   Variables, choose Import .env, and select `.env.vercel.local` for Production.

## Each deploy

- `npm run vercel:preview` deploys to a private preview URL.
- `npm run vercel:prod` deploys to the production URL.
- `npm run vercel:logs` shows the function logs.

Both deploy the local folder as it is, including uncommitted changes.

If a change adds a migration, run `npm run db:migrate` before deploying. The
function refuses to start on a database that is behind and names the fix.

## Limits on Vercel, and why

- **Uploads over 4.5 MB fail.** Vercel caps a function's request body at
  4.5 MB, and several of the public protocols in `backend/data/protocols` are
  larger. Railway has no such cap.
- **One extraction step can run for up to 300 seconds,** the most the Hobby
  plan allows. The two-step extraction the UI uses makes one request per pass.
  A 76-page protocol took 164 seconds in total over ten calls.
- **Uploaded PDFs are not kept.** The function can write only to `/tmp`, and
  that folder is cleared when the function instance stops. The text is stored in the
  database at upload, and everything the UI does reads it from there. Only the
  old one-shot `POST /extract` route reads the PDF file again.
- **Every extraction is a paid call** on the key in `LLM_API_KEY`. Re-running
  the same protocol is free, because results are cached in the database.
