# Decision log

Short architecture decision records: what was decided, why, and what it costs. Newest last.

## ADR-0001: Language models explain; deterministic code computes

**Context.** Loan and reward figures must be exactly right, and a model that "does the maths" will eventually be confidently wrong.
**Decision.** All money-critical numbers come from pure, versioned functions in `services/finance`. The assistant calls them as allow-listed tools and may only narrate the results. Any ₹ amount in a model reply that does not match a tool output to the paise causes the reply to be replaced with a safe message. Without a model, a deterministic "Tool mode" gives the same answers.
**Consequences.** Slightly less fluent answers; in exchange the calculator, the UI cards and the chat can never disagree, and the engine is unit-testable without any provider.

## ADR-0002: WhatsApp behind a gateway port; OpenWA for development, Meta Cloud API for production

**Context.** The product spec locks the *official* Meta WhatsApp Cloud API (template-approved business messaging). Obtaining Meta business verification and templates blocks development, so a self-hosted gateway (OpenWA) was integrated instead. OpenWA is **unofficial**: it drives WhatsApp through reverse-engineered clients, and its own documentation states there is "always a non-zero risk of account restriction or ban".
**Decision.** Application code depends only on the `WhatsAppGateway` protocol (`services/channels/gateway.py`). OpenWA is the one adapter and is documented as a **dev/demo gateway**, to be used only with a dedicated number. The production path is a Meta Cloud API adapter implementing the same protocol (an earlier Meta adapter existed before the switch; it should be re-implemented against the port, and needs Meta template approval).
**Consequences.** Swapping providers touches one module and one factory function; tests already exercise the port. Until a Meta adapter exists, WhatsApp must not be presented as a production channel.

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
