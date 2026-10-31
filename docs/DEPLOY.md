# Deployment

How to run VITRAM somewhere other than your laptop. The container images, compose file, migrations and backup scripts are
**verified locally** (see [`STATUS.md`](STATUS.md)); the hosted-platform blueprints in `deploy/` are **configuration only** and
have not been run by the author, so treat them as a starting point.

## Shape of a deployment

```
 browser ──HTTPS──► web (nginx, static SPA) ── /api ──► api (FastAPI, N replicas*) ──► PostgreSQL
                                                          ▲                                ▲
                          providers ── signed webhooks ───┘      worker (reminder loop) ───┘
                                                          api & worker share the /data volume (encrypted uploads)
```

\* **One API instance until uploads move off local disk.** Encrypted uploads are stored under `DATA_DIR/objects`, so every process
that serves documents needs the same volume. Workers don't read uploads and scale freely; the database carries all other state.

## Free-tier shape ($0): Cloudflare + Render + Neon

Everything below has a free plan. The trade-off is that the free API host sleeps when idle, so a cron keeps it awake.

```
 browser ─► Cloudflare Worker (static app, /api proxy, cron every 10 min) ─► Render free web service (API + in-process reminders)
                                                                              ├─► Neon free PostgreSQL     (DATABASE_URL)
                                                                              └─► Cloudflare R2 bucket     (STORAGE_BACKEND=s3, encrypted uploads)
```

| Piece | Where | Config |
|---|---|---|
| Web app, `/api` proxy, keep-awake cron | Cloudflare Worker, [`deploy/cloudflare/`](../deploy/cloudflare) | set `API_ORIGIN` in `wrangler.jsonc`; `npm run build` in `frontend`, then `npx wrangler deploy` |
| API (and the reminder loop) | Render free web service, `backend/Dockerfile` | `RUN_SCHEDULER=true` (no separate worker on the free plan), `AUTO_MIGRATE=true` |
| Database | Neon free PostgreSQL | `DATABASE_URL` (pooled connection string) |
| Uploads | Cloudflare R2 (S3 API) | `STORAGE_BACKEND=s3`, `S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` |

Files are Fernet-encrypted before they reach the bucket, so R2 only ever holds ciphertext. `APP_ORIGIN` and `PUBLIC_API_URL` are the
Worker's public URL, because the browser and providers' webhooks both reach the API through it.

Limits to expect: the first request after a long idle takes up to a minute while the API wakes; the Worker's free plan allows
100,000 API requests a day; Render's free plan gives 750 instance-hours a month, enough for one always-awake service.

## Configuration that must be right

The API **refuses to start** in `ENV=production` if these are wrong (`python -m app.doctor --offline` shows the same checks):

| Setting | Requirement |
|---|---|
| `VITRAM_DATA_KEY` | A Fernet key. Uploaded files are encrypted with it. `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. **Back it up separately: lose it and every upload is unreadable.** |
| `APP_ORIGIN` | The public `https://…` URL of the web app (the origin allowed to make state-changing requests; also used for deep links). `http://localhost` is allowed so a local compose demo works. |
| `SESSION_COOKIE_SECURE` | Leave unset (on in production). Only `false` on localhost. |

Recommended: `DATABASE_URL` (PostgreSQL; `postgres://…` is accepted), `RATE_LIMIT_BACKEND=database` with more than one API
process, `LOG_FORMAT=json`, `WHATSAPP_PROVIDER=meta`, and `RUN_SCHEDULER=false` on the API when a separate worker runs.

## TLS and proxies

Terminate TLS at your proxy and run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy address>` (the Dockerfile reads
`FORWARDED_ALLOW_IPS`). Then `request.url.scheme` is `https`, the session cookie is `Secure` and HSTS is sent. The bundled nginx
passes `X-Forwarded-Proto` through when an outer proxy already terminated TLS.

## Migrations

`AUTO_MIGRATE=true` (default) applies pending Alembic migrations at start-up: fine for a single instance, and an existing SQLite file is
backed up first. With several instances or a managed database, set `AUTO_MIGRATE=false` and run the release step instead:

```bash
python -m app.migrate status       # current vs head
python -m app.migrate upgrade      # or: alembic upgrade head
```

Take a backup first (below). Downgrades are manual (`alembic downgrade -1`) and never run automatically. `/api/ready` returns `503`
while the schema is behind the code, so an orchestrator won't route traffic to an un-migrated instance.

## Backups and restore

PostgreSQL holds the data; the volume holds the encrypted uploads. **A database dump alone is not a backup.**

```bash
DATABASE_URL=postgresql+psycopg://… DATA_DIR=/data backend/scripts/backup.sh ./backups
#  → vitram-<stamp>.dump        (pg_dump custom format)
#  → vitram-<stamp>-files.tgz   (the uploads)

# stop the API and worker, then:
DATABASE_URL=… DATA_DIR=/data backend/scripts/restore.sh vitram-<stamp>.dump vitram-<stamp>-files.tgz --yes
```

Rehearsed against PostgreSQL 16: the restored database matched the original table-for-table at the same schema revision, and the
restore refuses to run without `--yes`. Restore into a scratch database first; do this before you need it. For SQLite use
`python -m app.migrate backup | restore <file>`.

## Health, readiness and logs

| Endpoint | Use |
|---|---|
| `GET /api/health` | liveness: the process is up |
| `GET /api/ready` | readiness: database reachable and schema at the code's revision (`503` otherwise). The body also reports the reminder loop (`ok` / `stale` / `never_ran`) for alerting; a stalled worker doesn't make the API unready |

Every response carries `X-Request-ID` (an inbound one is reused if well-formed); every log line carries it too, and `LOG_FORMAT=json`
emits one JSON object per line. Redaction runs before formatting, so logs hold no phone numbers, e-mail addresses or card numbers.
Alert on: `/api/ready` ≠ 200, reminder loop `stale` for >5 minutes, and HTTP 5xx rate.

## Running it

**Containers (verified):** `cp .env.example .env`, set `VITRAM_DATA_KEY`, `docker compose up --build` → http://localhost:8080. That starts
PostgreSQL, the API (migrating on start), a **separate worker**, and nginx. `WEB_PORT` changes the port.

**Render:** `deploy/render.yaml` (database, API with a persistent disk, worker, static site with an `/api` rewrite). **Fly.io:**
`deploy/fly.api.toml` (API + worker processes, migrations as the `release_command`, a volume) and `deploy/fly.web.toml`. Both are
unverified: read them, set the secrets they list, and run `python -m app.doctor` against the result.

## Rollback

Redeploy the previous image. If a migration ran, restore the pre-release backup (or `alembic downgrade` if you've read the migration).
To stop outbound messages immediately without a deploy: set `RUN_SCHEDULER=false` and stop the worker, or clear `WHATSAPP_REMINDER_TEMPLATE`
(reminders then fall back to in-app).
