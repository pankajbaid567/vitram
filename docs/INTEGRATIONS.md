# Integration runbook

Every integration is optional and off by default: without credentials the app shows an honest *not configured* state. All secrets belong in the gitignored repository-root `.env` or a deployment secret manager. Never paste them into tickets, screenshots, logs, or this file.

## Gemini: Vitt Saathi and scanned PDFs

Set `GEMINI_API_KEY`, `GEMINI_MODEL` (text `generateContent`), and `GEMINI_LIVE_MODEL` (Live `bidiGenerateContent`). `/api/ai/status` reports configuration, not proof that a model call succeeded. The Live browser gets only an expiring token from `/api/ai/session-token`; it must never receive the long-lived API key. To allow AI-assisted document OCR, the user must separately grant `ai_processing` and `financial_documents` consent. OCR facts are low-confidence review candidates, not independently verified source text.

Safe smoke test: use a sample workspace and a fictional document. Ask a loan, card, EMI, insurance, and emergency question in English, Hindi, and Hinglish. Check exact amounts against calculator cards, source links, unknown terms, context isolation, and Tool-mode fallback when the provider is unavailable. Then allow microphone access, test Live audio in both directions, interruption, tool calls, transcript continuity and reconnect. Do not use real financial statements for initial provider tests.

Verification on 2026-09-23: the configured text model returned a response, the configured Live model returned audio over a WebSocket, the app's chat endpoint completed one tool-using turn on a fictional sample workspace, and OCR recovered an expected number from a fictional one-page image-only PDF. These narrow probes do not verify browser microphone capture/playback, voice interruption, multilingual financial safety, or real-document extraction quality.

## WhatsApp gateway (OpenWA, development only)

> **Read first.** The product specification calls for the *official* Meta WhatsApp Cloud API. This repository ships an adapter for [OpenWA](https://github.com/rmyndharis/OpenWA), a third-party, MIT-licensed, self-hosted gateway, **not included here** (clone it separately). OpenWA is *unofficial*: it connects through reverse-engineered clients, and its own README says there is always a non-zero risk of the WhatsApp account being restricted or banned. Use it **only with a dedicated test number**, never a personal or business number, and do not present it as a production channel (see [ADR-0002](DECISIONS.md)). The application talks to it only through the `WhatsAppGateway` port, so a Meta Cloud API adapter can replace it without touching callers.

Start OpenWA with its SQLite-friendly `.env.minimal` configuration, pair the dedicated number in the OpenWA dashboard, then create an operator API key scoped to that one session.

When running the backend in Docker Compose, `OPENWA_BASE_URL` must be reachable *from the container*, e.g. `http://host.docker.internal:2785`, not `127.0.0.1`.

Set `OPENWA_BASE_URL`, `OPENWA_API_KEY`, `OPENWA_SESSION_ID`, `OPENWA_WEBHOOK_SECRET`, and `PUBLIC_API_URL`. The API key is bearer-equivalent and must stay server-side. Use HTTPS outside localhost and keep redirects disabled so the key cannot be forwarded to another host. The webhook secret must be at least 16 characters.

Register this webhook in the paired OpenWA session:

```text
URL:    {PUBLIC_API_URL}/api/webhooks/openwa
Events: message.received, message.ack, message.failed
Secret: the exact OPENWA_WEBHOOK_SECRET value
Retries: 3
```

OpenWA signs the exact request bytes in `X-OpenWA-Signature`; VITTRM rejects missing or invalid signatures and deduplicates on `X-OpenWA-Idempotency-Key`. `message.received` powers STOP and Vitt Saathi replies. `message.ack`/`message.failed` update reminder delivery state. Group messages and unresolved `@lid` identities are deliberately ignored; enable OpenWA's `RESOLVE_LID_TO_PHONE=true` if the selected engine emits privacy IDs.

Before an outbound send, the user still needs a stored, Twilio-verified phone, WhatsApp consent and enabled reminder preference. The scheduler rechecks these at dispatch; STOP or in-app revocation converts queued WhatsApp reminders to in-app. Use only a controlled, opted-in test recipient. Verify send, delivery/read acknowledgements, inbound emergency query, deep link, duplicate webhook idempotency, invalid signature rejection, STOP and retry. Record provider message IDs/status only; never log message bodies or full phone numbers.

## Twilio Verify and consultation Voice

Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and a Verify v2 `TWILIO_VERIFY_SERVICE_SID` (prefix `VA`). Users request an SMS from the Profile page, then enter its code. A phone change clears verification and queued WhatsApp delivery. Verify setup is independent of a consultation call.

For calls, also set `TWILIO_FROM_NUMBER`, a team-controlled `CONSULTANT_PHONE_NUMBER`, and `PUBLIC_API_URL`. The status callback is `POST {PUBLIC_API_URL}/api/webhooks/twilio`. Trial accounts may restrict destination numbers. The request screen must show the context summary and number, with explicit consent. A live call to a saved or entered number requires that it match the user's verified phone. Test one consented call to a controlled number, consultant bridge, signed status transitions, failure/retry, and no recording. If any prerequisite is absent, VITTRM must not imply that a call happened.

## Deployment gate

For account email, configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` and `SMTP_FROM` with a trusted STARTTLS provider (`SMTP_USER` remains a legacy alias). Verify/reset links are single-use, SHA-256 hashed in storage and expire after 30 minutes. Password reset revokes all sessions. Test delivery, expiry, replay, unknown-address non-enumeration and provider outage before a public launch.

Use PostgreSQL and a persistent secret-managed `VITRAM_DATA_KEY`, HTTPS, a stable API URL, restricted provider keys, backed-up Alembic upgrades, restore rehearsal, production monitoring and an approved retention/deletion policy. Do not expose fictional catalogues as live offers. Live channels remain off until the complete consent, verification, destination, signature and rollback checks pass.

API references: [Gemini PDF understanding](https://ai.google.dev/gemini-api/docs/document-processing), [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output), [Twilio Verify start](https://www.twilio.com/docs/verify/api/verification), [Twilio Verify check](https://www.twilio.com/docs/verify/api/verification-check).
