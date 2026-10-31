# Completion checklist

Scope: everything that can be **built and verified without your phone, your provider keys or a hosting account**, so that the only thing left for you is to plug in credentials and run the live checks in `GO_LIVE.md`.
Each item has an acceptance test ("done when"). `[ ]` open · `[x]` done and verified. Items marked **YOU** cannot be done by me.

---

## Phase 0 — Unblock (CI is red)

- [x] **0.1 Reproduce CI on Linux.** Two tests only pass on macOS because they rely on Apple Vision being the default OCR provider (`test_scanned_policy_marks_ocr_facts_for_review`, `test_receipt_photo_end_to_end`). *Done when:* both pass in a clean `python:3.12` container.
- [x] **0.2 Reproduce the PostgreSQL job** the same way (service container) and fix whatever fails. *Done when:* the full suite passes against Postgres 16 in the container.
- [x] **0.3 Tests never depend on the host.** One autouse fixture pins OCR/provider settings; no test reads `OCR_PROVIDER=auto`. *Done when:* the suite is identical on macOS and Linux.
- [ ] **0.4 CI green on GitHub** (checked through the Actions API after the push).
- [x] **0.5 Add a CI badge** to the README.

## Phase 1 — Close the specification gaps

- [x] **1.1 Meta WhatsApp Cloud API adapter** (the spec's locked decision) behind the existing `WhatsAppGateway` port:
  - send: template message for business-initiated reminders (configurable template name/language), free text only inside the 24-hour reply window;
  - webhook: `GET` verification challenge (`hub.verify_token`), `POST` signature check (`X-Hub-Signature-256`, HMAC-SHA256 over raw bytes), parse messages + statuses;
  - settings `WHATSAPP_PROVIDER=meta|openwa`, token, phone-number id, app secret, verify token, template; startup validation;
  - *Done when:* contract tests with mocked HTTP cover send, template vs. free text, signature accept/reject, verification challenge, status mapping, error mapping (retryable vs. not); the same inbound/STOP/idempotency behaviour passes for both providers via a shared parametrised test.
- [x] **1.2 Provider-neutral webhook routes** (`/api/webhooks/whatsapp` plus the existing `/openwa` kept for compatibility); docs updated.
- [x] **1.3 Bounded AI extraction for policies and loan documents** (spec D2/D3): when Gemini and consent are present, extract structured facts, then **reject any value whose text isn't found on the cited page**; heuristic facts and user corrections always win; conflicts are surfaced. *Done when:* tests with a fake model prove: valid facts accepted, hallucinated values dropped, corrections preserved, injection text ignored, failure falls back to heuristics.
- [x] **1.4 Card statement reconciliation** (spec D4): user-confirmed purchase rows map to categories and feed *cycle spend / reward estimates* with provenance, reversible; unconfirmed rows never count. *Done when:* API tests cover confirm, reject, undo, and ranking changes.
- [x] **1.5 Privacy controls beyond "delete my data":** `GET /api/profile/export` (full JSON export) and `DELETE /api/auth/account` (removes the login too, revokes sessions, deletes files, writes an audit line without personal data). *Done when:* tests prove another user's data is untouched and storage objects are gone.
- [x] **1.6 Response-contract audit** (spec Q1): one test walks every journey route and asserts currency, precision, citations present for material facts, catalogue `is_mock`/date labels, calculation `formula_version` and inputs. *Done when:* the test fails if any route drops them.
- [x] **1.7 Calculation snapshots** (spec S7): every calculator route persists a `CalculationRun` (inputs, outputs, version) and the assistant cites its id. *Done when:* a test enumerates the routes.
- [x] **1.8 Reminder settings explain themselves:** the preferences API returns *why* WhatsApp is off (the same reason the dispatcher uses); the settings screen shows it.
- [x] **1.9 `lang` metadata** on Hindi/Hinglish text (spec accessibility gap) and Devanagari font fallback checked.

## Phase 2 — Operability and system design

- [x] **2.1 Dedicated worker process:** `python -m app.worker` runs the reminder loop; `RUN_SCHEDULER=false` disables it in the API; compose gets a `worker` service. *Done when:* a test starts one worker and one "API" and a reminder is sent once.
- [x] **2.2 Health and readiness:** `/api/health` (liveness) and `/api/ready` (database reachable, migrations at head, scheduler heartbeat recent). *Done when:* readiness goes false when the DB is unreachable (tested).
- [x] **2.3 Request IDs and structured logs:** `X-Request-ID` in and out, JSON logs option, redaction preserved. *Done when:* a test shows the id in the response and log record, and no PII.
- [x] **2.4 Global error handler:** unexpected exceptions return the stable error shape with a request id and never leak internals. *Done when:* a forced error test passes.
- [x] **2.5 Fail-fast production config:** the app refuses to start in `ENV=production` without `VITRAM_DATA_KEY`, an `https` `APP_ORIGIN`, and with `AUTO_MIGRATE` guidance; clear message. *Done when:* tested.
- [x] **2.6 Shared rate limiting** that holds across workers (database-backed limiter behind the same interface, selected by setting). *Done when:* two limiter instances on one database share counts (tested).
- [x] **2.7 `python -m app.doctor`:** a read-only self-check that reports, per integration, *configured?* and *reachable?* (Gemini model list, OpenWA session status, Meta webhook config, Twilio Verify service lookup, SMTP connect, database, migrations) with secrets never printed. This is the tool you run when integrating.
- [x] **2.8 PostgreSQL backup/restore** script and documented rehearsal (`pg_dump`/restore), tested in the container.
- [x] **2.9 Performance guardrails:** indexes reviewed for the hot queries (transactions by user/date, reminders by status/schedule, facts by document); a smoke test that a 12-month statement processes within a bound.

## Phase 3 — Quality and tests

- [x] **3.1 Twilio voice and consultation tests** (coverage 42 % today): create, failure, retry, cancel, status callbacks, signature, no-recording TwiML, "no call placed" honesty. Mocked HTTP.
- [x] **3.2 Gemini adapter outage/edge tests:** timeout, malformed tool call, cooldown, numeric-fidelity replacement, language handling.
- [x] **3.3 Cross-user isolation matrix:** one parametrised test that hits *every* object-scoped route as a second user and expects 404.
- [x] **3.4 Coverage:** backend ≥ 88 %, with the weakest modules (`twilio_voice`, `consultations`, `webhooks`, `replies`, `family`) ≥ 80 %.
- [x] **3.5 Frontend tests:** loans results, emergency mode, reminder settings, API error/401 handling, upload flow. Fix or justify all 19 lint warnings.
- [x] **3.6 End-to-end smoke in a real browser** (`frontend/scripts/e2e.mjs`): sample workspace → documents → loan results → real cost → card optimiser → emergency mode, with assertions; runs in CI against the compose stack.
- [x] **3.7 Accessibility audit re-run** after UI changes (target: 0 violations, 8/8 keyboard) and the high-contrast/lang items from the spec.
- [x] **3.8 Dependency hygiene:** `pip-audit` and `npm audit` clean or documented; Dependabot config; both added to CI.
- [x] **3.9 Linux/macOS parity:** the container reproduction in 0.1 becomes a documented `make ci` target.

## Phase 4 — Repository and developer experience

- [x] **4.1 `Makefile`** (`make dev test lint ci up down`), `.editorconfig`, pre-commit config (ruff, whitespace).
- [x] **4.2 `docs/API.md` + exported `openapi.json`** (generated by a script; CI fails if stale).
- [x] **4.3 `SECURITY.md`** (reporting, supported scope, known limits) and a short `CONTRIBUTING.md`.
- [ ] **4.4 LICENSE — YOU decide** (I'll add MIT if you say so). Note OpenWA is a separate MIT project, not included.
- [x] **4.5 Deployment blueprint** (`render.yaml` and a Fly.io `fly.toml`), `docs/DEPLOY.md`: env, TLS, `--proxy-headers`, migrations as a release step, backups, rollback. *Config only; unverified until you deploy.*
- [x] **4.6 Docs refresh:** `ARCHITECTURE` (worker, readiness, Meta adapter), `DECISIONS` (ADR for Meta, worker split, limiter), `STATUS` (every new item with its evidence), `INTEGRATIONS` (Meta setup), README updated.

## Phase 5 — Verification and hand-off

- [x] **5.1 Full matrix green:** backend on SQLite and PostgreSQL, in a Linux container, frontend, e2e smoke, a11y, ruff, audits.
- [x] **5.2 Compose stack with a separate worker** brought up and exercised through nginx.
- [ ] **5.3 Push in logical commits; CI green on GitHub** (confirmed via the API).
- [x] **5.4 `docs/GO_LIVE.md`:** the exact order for you to integrate — which keys to set, which `app.doctor` line should turn green after each, the controlled live test for each channel, expected results, rollback. Includes the Meta business-verification/template checklist.
- [ ] **5.5 Update `RESUME_AUDIT.md`** (local) with final numbers and re-draft the resume bullets from what is then true.

---

## Needs you (cannot be done by me)

| Item | Why |
|---|---|
| Gemini key checks (chat, languages, voice mic, vision OCR) | Needs a key and a microphone |
| WhatsApp: OpenWA pairing (spare number) and/or Meta business verification + template approval | Needs your phone / Meta account |
| Twilio Verify SMS and one consultation call | Needs credentials and a controlled number |
| SMTP delivery check | Needs credentials |
| Hosting account and the live URL | Needs your account |
| Demo video / GIF | Needs a screen recording |
| Screen-reader pass (VoiceOver/NVDA) | Manual |
| Rotating the keys in `.env` | You chose to keep them; revisit before any shared deployment |
| License choice | Your decision |
| Real lender/issuer/insurer data and regulatory review | Out of prototype scope; catalogues stay labelled as samples |

## Explicitly out of scope

Real bank/account-aggregator feeds, lender or insurer application hand-offs, claim-status integrations, OTP/social login, multi-tenant admin, native mobile apps (all listed as "full vision / after hackathon" in the spec).
