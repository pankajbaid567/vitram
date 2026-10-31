# Decision log

Short architecture decision records: what was decided, why, and what it costs. Newest last.

## ADR-0001: Language models explain; deterministic code computes

**Context.** Loan and reward figures must be exactly right, and a model that "does the maths" will eventually be confidently wrong.
**Decision.** All money-critical numbers come from pure, versioned functions in `services/finance`. The assistant calls them as allow-listed tools and may only narrate the results. Any ₹ amount in a model reply that does not match a tool output to the paise causes the reply to be replaced with a safe message. Without a model, a deterministic "Tool mode" gives the same answers.
**Consequences.** Slightly less fluent answers; in exchange the calculator, the UI cards and the chat can never disagree, and the engine is unit-testable without any provider.

## ADR-0002: WhatsApp behind a gateway port: Meta Cloud API for production, OpenWA for development

**Context.** The product spec locks the *official* Meta WhatsApp Cloud API (template-approved business messaging). Meta business verification and template approval take time, so a self-hosted gateway (OpenWA) was integrated first to build and demo the flows. OpenWA is **unofficial**: it drives WhatsApp through reverse-engineered clients, and its own documentation states there is "always a non-zero risk of account restriction or ban".
**Decision.** Application code depends only on the `WhatsAppGateway` protocol (`services/channels/gateway.py`). Two adapters implement it and `WHATSAPP_PROVIDER` selects one: `meta_cloud.py` (official; reminders are approved *template* messages, replies are free text inside the 24-hour window, webhooks signed with `X-Hub-Signature-256` and subscribed through the `GET` handshake) and `openwa.py` (dev/demo only, dedicated number). One shared parametrised test suite runs the same webhook scenarios against both.
**Consequences.** Switching provider is configuration. Production must use `meta` and needs an approved template (`docs/INTEGRATIONS.md`). Both adapters are verified against mocked HTTP only until live credentials are used (`docs/STATUS.md`).

## ADR-0003: Consent is re-checked at the moment of sending

**Context.** A reminder can be queued days before it is due; the user may revoke consent, change their number, or reply `STOP` in between.
**Decision.** `whatsapp_block_reason()` re-evaluates preference, number, verification and consent inside `dispatch()`. `STOP` revokes consent and downgrades queued WhatsApp reminders to in-app. The in-app notification is always created. User-visible copy is generated from the actual outcome (`describe_dispatch`), so the UI never claims a WhatsApp send that did not happen.
**Consequences.** One extra consent lookup per send; no stale authorisation.

## ADR-0004: Webhook idempotency through a database unique key

**Context.** Providers redeliver webhooks at-least-once, possibly to several workers.
**Decision.** Record each event under a unique `(provider, external_id)` inside a savepoint; the constraint, not process memory, decides who processes it. Verify the HMAC over the raw bytes before parsing. Delivery receipts may only move forward (`sent → delivered → read`), failure is terminal (`channels/delivery.py`).
**Consequences.** Correct with any number of workers and across restarts; receipts that arrive out of order cannot regress state.

## ADR-0005: The reminder queue is a database table with atomic claims

**Context.** The reminder loop used to `SELECT` due rows and send them, so two workers could send the same reminder.
**Decision.** Keep the queue in PostgreSQL/SQLite, and claim rows with a conditional `UPDATE … WHERE status = 'scheduled'`, committed *before* sending (`claim_due`). A claim carries `claimed_at`; one older than 5 minutes belongs to a crashed worker and can be taken over. Retryable failures return to `scheduled` with back-off.
**Alternatives rejected.** A broker (Redis/RabbitMQ): another service to operate for a few hundred reminders a day. `SELECT … FOR UPDATE SKIP LOCKED`: PostgreSQL-only, and the project also runs on SQLite.
**Consequences.** Several workers are safe today. At-most-once is preferred to at-least-once for *sending*; a worker that crashes after the gateway accepted the message but before committing could send twice after the TTL (documented trade-off). Scaling further means a dedicated worker process, then a broker.

## ADR-0006: SQLite by default, PostgreSQL in production, Alembic for both

**Decision.** Zero-setup local runs on SQLite; deployments use PostgreSQL. Alembic owns the schema; pending migrations apply at start-up unless `AUTO_MIGRATE=false`, and an existing SQLite file is backed up first. The test suite and the migration chain run on both databases in CI.
**Why it matters.** Running on a real PostgreSQL found two defects SQLite hid: a data migration used `LIKE`/`REPLACE` on JSON columns, and Pillow was imported but not declared as a runtime dependency (it only arrived through a dev-only package).

## ADR-0007: Privacy by purpose

**Decision.** Each journey receives only the profile fields it needs (`services/slices.py`), and each assistant context has its own tool allow-list. Insurance never sees transactions; loans never see family details. Consent is recorded per purpose and is revocable. Raw documents are never sent to the model; extracted facts are.
**Consequences.** More plumbing, but context isolation is testable (and tested).

## ADR-0008: Read scans on the device by default

**Decision.** OCR defaults to Apple Vision through a small Swift helper, so scans never leave the machine. Cloud OCR (Gemini) is available only when explicitly configured and with the user's AI-processing consent. Extracted values from scans are marked low-confidence and require review.
**Consequences.** Offline OCR is macOS-only; Linux deployments need the opt-in cloud provider or no scan support (the app says so plainly instead of returning empty results).

## ADR-0009: Run the reminder loop in a separate worker, and make readiness honest

**Context.** The reminder dispatcher ran inside the web process. That couples sending to HTTP deploys and gives operators no way to see a stalled loop.
**Decision.** `python -m app.worker` runs the same loop with no HTTP; `RUN_SCHEDULER=false` turns it off in the API. Each pass writes a row to `worker_heartbeats`. `/api/ready` returns `503` only for things that make *the API* unfit to serve (database down, schema behind the code) and *reports* the loop's state (`ok`/`stale`/`never_ran`) for alerting.
**Consequences.** API and worker scale and restart independently; a dead worker is visible rather than silent, without taking the API out of rotation. Running both in one process still works for development.

## ADR-0010: AI proposes, code verifies, deterministic extraction wins

**Context.** Pattern matching misses fields; a model can find them but can also invent them, and a document can contain instructions aimed at it.
**Decision.** The model only proposes `{key, value, page, quote}` for an allow-list of fields. A proposal is accepted only if the quote is verbatim on the cited page, supports the value, and is not injection-shaped. Accepted values fill gaps; they never overwrite a deterministic fact, and disagreements surface as warnings. Off by default (it sends text to Google), gated by operator setting *and* the user's consents, and every failure degrades to pattern matching.
**Consequences.** Higher recall with the same safety property as the rest of the system: nothing shown to the user is unsourced.

## ADR-0011: Rate limits behind one interface, two backends

**Decision.** `ratelimit.limiter()` returns an in-memory sliding window (default, zero infrastructure, bounded memory) or a database-backed one (`RATE_LIMIT_BACKEND=database`) that records an attempt before counting it, so concurrent requests can be over-refused at the margin but never over-admitted, the safe direction for a brute-force guard.
**Consequences.** Single-process deployments need nothing; scaled-out ones flip one setting. A Redis backend would be a third implementation of the same two-method interface.

## ADR-0012: Confirmed statement purchases feed rewards through a separate, reversible record

**Context.** Card-statement purchase rows are low-confidence extractions, but they are exactly what a reward cap needs ("how much of this month's cap is used?").
**Decision.** Only user-confirmed rows count; they are grouped by category into `UserCard.imported_spend` (with document provenance) rather than overwriting the user's own `cycle_spend`. Reward maths uses the sum. The import is previewable, undoable, withdrawn when the statement is deleted or re-read, and replacing one statement with another needs explicit consent.
**Consequences.** Manual and imported figures never silently mix; every number can be traced to a statement row the user approved.

## ADR-0013: Storage is a port with a local and an S3 adapter

**Context.** Free hosts have no persistent disk, but uploads were written to `DATA_DIR`. **Decision.** `services/storage.py`
keeps one contract (`put`/`get`/`delete`, ciphertext only, random keys) with `local` and `s3` backends chosen by
`STORAGE_BACKEND`; R2 (S3-compatible) serves the free deployment. **Consequences.** No caller changed; the bucket never sees
plaintext; boto3 is an optional extra; moving between backends needs a copy of existing objects.
