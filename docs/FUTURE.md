# Future work: scale, concurrency, system design and depth

Ordered by **value per hour of work**. Every item says what is true today, what to build, how to know it worked
(a number or a test, not a feeling) and what it teaches. Do them roughly in order; P0 first.

Status words: **Today** = verified in the code at the time of writing.

---

## Where the system stands today (honest baseline)

| Area | Today | Weak spot |
|---|---|---|
| Document processing | `Ingest → Parse → Normalise → Validate → Persist` runs as a FastAPI background task inside the API process (`services/pipeline.py`). Stage and status are persisted; the UI can Retry. | Not durable. If the API restarts or the free host sleeps mid-run, the job is stranded until a user presses Retry. It also competes with request handling for CPU. |
| Reminders | DB-claimed jobs with expiring claims, several workers are safe (`app/worker.py`). | Good. The same pattern is not used for documents or inbound webhooks. |
| Inbound WhatsApp | Handled inside the webhook request. | Slow work inside a request the gateway is waiting on. |
| Rate limiting | Per-process memory by default, shared DB backend optional (`app/ratelimit.py`). | The default is per instance, and only sign-in/recovery endpoints are covered. Nothing limits the expensive AI and upload endpoints per user. |
| Caching | Almost none. Profile and dashboard figures are recomputed. | Repeated reads cost repeated CPU and queries. |
| Database | PostgreSQL (Neon) in production, SQLite locally, 36 tables, 11 migrations. | No index review, no query-count tests, no `EXPLAIN` evidence. |
| Observability | Request id on every log line, `/api/health`, `/api/ready`, doctor command. | No metrics, no traces, no alerts, no SLOs. |
| Load | Never load-tested. | No numbers to quote. |
| Retrieval | BM25 over page chunks. | No quality measurement. |
| Docs | `ARCHITECTURE.md` "Scaling path" still says uploads are local-disk only. | Out of date: R2 object storage now exists. Fix with the first change you make. |

---

## P0: do these first (highest signal, mostly small)

### 1. Measure it: load test and publish the numbers
**Why first:** every later item needs a baseline, and "handles N req/s at p95 X ms" is the single most useful line for a resume.
- Add `loadtest/` with **k6** scripts: sign-in, dashboard read, loan options, card recommendation, document upload, assistant question.
- Run against a local Docker Compose stack (Postgres), then against the free deployment. Record p50/p95/p99, error rate, saturation point.
- Profile the slowest endpoint (`py-spy` or `pyinstrument`) and fix the top hotspot. Re-measure. Keep a before/after table in `docs/PERFORMANCE.md`.
- Define two SLOs, e.g. "95% of reads under 300 ms", "99% of uploads processed within 60 s", and check them in the test.

**Done when:** `docs/PERFORMANCE.md` has a table of numbers, the hardware/plan they were measured on, and one real optimisation with a before/after.
**Teaches:** latency percentiles, Little's law, capacity planning, profiling.

### 2. Make document processing durable (job queue)
**Why:** this is the biggest real design flaw and the best interview story.
- Add a `jobs` table (id, type, payload, status, attempts, run_after, locked_by, locked_until, error, created_at) and claim with
  `SELECT … FOR UPDATE SKIP LOCKED` (Postgres) so many workers never take the same job. Reuse the claim/expiry idea from the reminder worker.
- Upload endpoint only stores the file, inserts a job and returns `202` with a job id. A worker (same image, `python -m app.worker`) runs the pipeline.
- Retries with exponential backoff and jitter, a max-attempts limit, and a **dead-letter** state that the UI shows with a Retry button.
- Make every stage **idempotent** (re-running a stage must not duplicate rows). Test it by killing the worker mid-stage.
- Keep the `JobQueue` behind an interface so Redis/SQS could replace it later (SQLite fallback for local dev).

**Done when:** a test kills the worker mid-job and the job finishes exactly once afterwards; two workers on 100 jobs process each exactly once.
**Teaches:** at-least-once delivery, idempotency, visibility timeouts, dead-letter queues, `SKIP LOCKED`.

### 3. Database depth: indexes, query counts, pagination
- Run with `pg_stat_statements` on a seeded database (10k+ rows per user-owned table) and list the ten slowest/most frequent queries.
- `EXPLAIN (ANALYZE, BUFFERS)` each; add composite indexes that match real filters (`user_id` + date, `user_id` + status). Write an Alembic migration per index and note the plan change in the migration docstring.
- Add **query-count tests**: an endpoint must not issue more than N queries regardless of row count (catches N+1 forever).
- Move list endpoints to **keyset pagination** (`WHERE (created_at, id) < (…) ORDER BY … LIMIT n`) instead of offset.
- Check pool settings against Neon's pooled endpoint (pool size, `pool_pre_ping`, statement timeout, `idle_in_transaction_session_timeout`).

**Done when:** a before/after of at least one query going from a sequential scan to an index scan, and a test that fails if an N+1 is introduced.
**Teaches:** query plans, composite index order, N+1, pagination trade-offs, connection pooling.

### 4. Idempotency and concurrent-edit safety
- `Idempotency-Key` header on mutating endpoints that must not run twice (upload, consent change, sending a message, delete account). Store key → response for 24 h.
- **Optimistic concurrency** on user-editable records (profile facts, EMIs, goals): a `version` column and `If-Match`/ETag; a stale write returns `409` and the UI shows a merge prompt.
- Tests that fire the same request ten times in parallel and assert one effect, and two conflicting edits and assert one `409`.

**Done when:** the parallel tests pass on PostgreSQL.
**Teaches:** race conditions, lost updates, idempotent APIs, ETags.

---

## P1: next (these turn a good project into a deep one)

### 5. Observability: metrics, traces, alerts
- **OpenTelemetry** traces across API → DB → storage → gateway; propagate the existing request id as the trace id.
- Prometheus-style metrics: request rate/errors/duration by route (RED), queue depth, job age, reminder lag, gateway failure rate, per-stage pipeline duration.
- A small Grafana (or Grafana Cloud free) dashboard committed as JSON, plus **alert rules** (queue age > 5 min, error rate > 2%, `/api/ready` failing).
- Error tracking (Sentry free tier) with the request id attached.

**Done when:** you can show a screenshot of a trace from upload to processed document and an alert that fired in a failure drill.

### 6. Resilience patterns for outside dependencies
- **Circuit breaker** (closed → open → half-open) around Gemini, OpenWA/Meta and R2, replacing the fixed 60 s cool-off.
- Timeouts everywhere, a **retry budget** (never retry more than ~10% of traffic), jitter, and a **bulkhead** so a slow AI call cannot exhaust the thread pool that serves reads.
- **Load shedding**: when queue depth or latency crosses a threshold, return `503` with `Retry-After` for expensive endpoints before the system collapses.
- **Chaos tests**: inject failures (gateway 500, DB slow, storage timeout) and assert the documented behaviour in the "Failure behaviour" table.

**Teaches:** cascading failure, backpressure, graceful degradation.

### 7. Inbound webhooks: acknowledge fast, process later
- Verify the signature, write the raw event to an `inbound_events` table with a unique key (already de-duplicates), return `200` immediately, and let a worker do the work.
- Outbound sends go through a transactional **outbox**: the reminder row and the "send" intent commit together, a relay sends and marks it. This removes the "sent but not recorded / recorded but not sent" gap.

**Teaches:** transactional outbox, exactly-once-effect over at-least-once delivery.

### 8. Rate limiting and abuse control, properly
- Token-bucket per user and per IP, kept in a shared store (Postgres now, Redis later), with different budgets for cheap reads, uploads and AI questions, plus a daily AI-cost cap per user.
- Mirror the coarse limits at the edge with **Cloudflare rate-limiting/WAF rules**, so abusive traffic never reaches the free API host.
- Return standard `RateLimit-*` and `Retry-After` headers; test the limiter under concurrency.

### 9. Caching strategy
- **Compute snapshots**: store the dashboard/profile result with a version and invalidate when its inputs change (the versioned snapshots already hint at this design).
- HTTP caching with `ETag`/`304` for read endpoints; long cache for catalogues keyed by catalogue version.
- If a shared cache is justified by the load test, add Redis (Upstash free tier) behind a `Cache` interface; show the hit rate and the latency gain.

**Done when:** the load test shows a measurable drop in p95 for dashboard reads and the invalidation is covered by tests (stale data is the real risk).

### 10. Retrieval quality, measured
- Build a **golden set** of ~100 questions over the sample documents with the expected page/fact.
- Report recall@k and MRR for BM25 today, then add **pgvector** embeddings with hybrid ranking (BM25 + vector, reciprocal rank fusion) and compare.
- An LLM **evaluation harness** for the assistant: faithfulness (no amount outside tool results), refusal when `found:false`, prompt-injection cases. Run in CI on a small sample.

**Teaches:** information-retrieval evaluation, hybrid search, regression testing for LLM features.

---

## P2: depth and engineering maturity

### 11. Defence in depth for data isolation
- PostgreSQL **Row Level Security** keyed on a per-request `app.user_id` setting, so a missing `WHERE user_id = …` cannot leak another user's rows.
- Extend the generated access matrix with an automated "user A cannot read user B" sweep on **every** route, run against Postgres.

### 12. Encryption key management
- Move from a single Fernet key to **envelope encryption**: a per-user data key wrapped by a master key (`MultiFernet` for rotation now, a cloud KMS later).
- A tested **key-rotation** procedure (re-wrap, no downtime) and a restore drill that proves backups decrypt.

### 13. Stronger correctness testing
- **Property-based tests** (Hypothesis) for the finance engine: EMI schedule sums to principal, interest never negative, prepayment never increases total cost.
- **Mutation testing** (`mutmut`) on `services/finance` to show the tests actually catch bugs.
- Contract tests between the OpenAPI schema and the frontend types (generate the client, fail CI on drift).

### 14. Delivery and operations
- **Expand/contract migrations** documented and enforced (never drop a column in the same release that stops using it).
- Per-PR **preview deployments** (Cloudflare Worker version + a branch database on Neon).
- Feature flags for risky changes; a documented rollback that was actually rehearsed.
- Infrastructure described as code (`wrangler.jsonc` is a start; add Render blueprint `render.yaml`).
- Scheduled automated **backup + restore verification** that fails loudly.

### 15. Security hardening
- Short threat model (STRIDE table) in `docs/SECURITY.md`; dependency and container scanning in CI; SBOM; `Content-Security-Policy` with a report endpoint.
- Session hardening: rotation on privilege change, device list with remote sign-out, step-up check before export/delete.

---

## P3: product depth (pick what fits your story)

- **Real-time progress**: Server-Sent Events for document processing instead of polling.
- **Official WhatsApp** through Meta Cloud API and message templates; keep OpenWA as the dev gateway only.
- **PWA / offline** read of the last dashboard; Hindi navigation labels; empty-state illustrations; a ⌘K shortcut sheet (see `UX_REVIEW.md`).
- **Real data source**: replace `load_catalogues()` with a real provider or the RBI/IRDAI public data, keeping the "labelled sample vs reference" contract.
- **Multi-region read path**: only if the load test proves latency from India to the US host is the bottleneck (it likely is; Neon `ap-south-1` plus a Mumbai/Singapore API host is the cheap fix, and a good measured before/after).

---

## Suggested order of attack (about 4 weeks, evenings)

| Week | Items | Output you can show |
|---|---|---|
| 1 | 1 load test, 3 indexes and query counts | `PERFORMANCE.md` with real numbers and one fixed hotspot |
| 2 | 2 durable job queue, 4 idempotency | Kill-the-worker test, parallel-request tests |
| 3 | 5 observability, 6 resilience, 7 webhooks/outbox | Trace screenshot, chaos tests, alert |
| 4 | 9 caching, 10 retrieval eval, 8 rate limits | Before/after latency, recall@k table |

## How to talk about it in an interview

1. Start with the problem you found ("document jobs were lost on restart"), not the tool.
2. State the guarantee you chose (at-least-once + idempotent stages) and why not exactly-once.
3. Give one number from your own measurements (p95, queue age, recall@k).
4. Name the trade-off you accepted (Postgres queue instead of Kafka: fewer moving parts at this scale; the interface allows swapping).
5. Say what you would change at 100× the load. The honest answer is in this file.
