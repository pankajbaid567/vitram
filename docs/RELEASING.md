# Releasing safely

How a change reaches production without downtime or data loss, and how to undo it. Everything here is exercised by a test or a script, not just described.

## The pipeline

1. **Pull request:** CI runs backend tests on SQLite *and* PostgreSQL, frontend lint/typecheck/tests/build, a dependency audit, and the Chrome end-to-end
   journeys (desktop and 390 px) plus an accessibility audit. A **preview** of the web app is uploaded as its own Worker version when Cloudflare secrets exist
   (`.github/workflows/preview.yml`).
2. **Merge to `main`:** Render rebuilds and deploys the API (health check `/api/ready`); the API runs pending migrations on start (`AUTO_MIGRATE=true`) and refuses
   to serve if the schema is behind. The web app is deployed with `npx wrangler deploy` from `deploy/cloudflare` (infrastructure is code: `wrangler.jsonc`,
   `deploy/render/render.yaml`).
3. **Verify in a browser:** `node scripts/e2e.mjs --base <url>` and `e2e-journey.mjs` (set `WAIT_SCALE=4` against a cold free host).

## Expand / contract migrations (enforced)

During a deploy the old and new code run against the same database, so a migration shipped with new code may only **expand** the schema: new tables, new
nullable or defaulted columns, new indexes. Dropping or renaming a column or table, or making a column `NOT NULL` without a default, is a **contract** step
that must wait until no running code uses the old shape: ship the code change in one release, the contraction in a later one.
`tests/test_migration_policy.py` parses every migration from `0012` on and fails the build if one contains a destructive operation without a `CONTRACT:` line in its
docstring explaining why the previous release still works.

## Rollback

| What went wrong | Do this | Why it is safe |
|---|---|---|
| Bad code, schema fine | Redeploy the previous commit (Render dashboard or `git revert` + push) | every migration since `0011` only expanded the schema, so the previous release runs on the newer schema |
| Bad migration | `python -m app.migrate downgrade 0011` (the previous release's revision), then redeploy the old code | rehearsed by `tests/test_migration_roundtrip.py` (SQLite) and, by hand, on PostgreSQL: `up → 0016`, `down → 0011` (jobs, idempotency and version columns gone, policies dropped), `up → 0016` again, data intact |
| Bad data change | restore the last backup (`scripts/restore.sh`) | `scripts/verify_backup.sh` proves backups restore, weekly in CI |
| Bad feature | switch it off by setting, no deploy: `CACHE_ENABLED`, `THROTTLE_ENABLED`, `RETRIEVAL_MODE`, `RLS_ENABLED` | each setting is a feature flag with a safe fallback |

The reminder loop and the job workers are idempotent, so a rolled-back release that left jobs queued simply has them picked up by whichever version runs next.

## Backups you can trust

`scripts/backup.sh` dumps PostgreSQL (custom format) and the encrypted uploads; the master key is backed up separately on purpose.
`scripts/verify_backup.sh` restores a dump into a scratch database and compares **every table by row count and checksum** (`compare_databases.py`); the
weekly `backup-verify` workflow runs it against a seeded database. Verified locally on 39 tables / 1,382 rows: identical; and a deliberately tampered row is
detected (negative control).

## Observability during a release

`/api/ready` reports database, migration state, job-queue depth and the age of the oldest waiting job. Alerts (`deploy/observability/alerts.yml`) fire on error
rate, p95 latency, a stalled queue and dead jobs. A release that breaks document processing shows up as `JobQueueStalled` or `DeadJobs` within minutes.

## Not done (honest list)

* Per-branch API and database previews (the preview uses the production API). A Neon branch database per PR plus a throwaway Render service is the next step.
* Blue/green or canary traffic splitting: the free tier has one API instance, so a deploy briefly restarts it (the Worker returns a friendly 502 and the
  browser retries).
