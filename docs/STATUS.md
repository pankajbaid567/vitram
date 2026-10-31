# Verification status

What has actually been run, and what has not. Last full pass: **2026-10-31** (macOS, SQLite and PostgreSQL 16, Chrome headless).
"Verified" means observed working, not merely implemented. Anything needing a phone, a provider key or a physical device is listed under *Not verified* rather than claimed.

## Automated checks

| Check | Result | Command |
|---|---|---|
| Backend tests | 177 pass | `cd backend && uv run pytest -q` |
| Backend on PostgreSQL 16 | pass (migration tests are SQLite-specific) | `TEST_DATABASE_URL=postgresql+psycopg://… uv run pytest -q --deselect tests/test_migrations.py` |
| Backend coverage | 84 % (7.8k statements) | `uv run pytest -q --cov=app` |
| Backend lint | clean | `uv run ruff check .` |
| Frontend tests | 31 pass | `cd frontend && npm test` |
| Typecheck, lint, build | pass; lint has warnings only | `npm run typecheck && npm run lint && npm run build` |
| Migrations | `0001 → 0008` apply on empty SQLite and PostgreSQL; 0007 also verified on PostgreSQL with data | `uv run python -m app.migrate upgrade` |
| Container stack | `docker compose up` (nginx → API → PostgreSQL) serves the SPA, the API and the demo workspace | see README |
| Accessibility | project audit: **81 axe scans** (every route, desktop and mobile), **0 violations**, 8/8 keyboard and touch checks. Screen-reader testing is still manual | `node --experimental-websocket frontend/scripts/a11y-audit.mjs` (Node 20) |

## Journeys observed working end to end (sample workspace and a fresh user)

| Journey | Evidence |
|---|---|
| Sign-up, login, logout, session | API + browser |
| Statement upload (CSV, text-PDF) → profile | 260-row CSV parsed; totals reconcile to the paisa against an independent recomputation (₹6,98,163.14 out, ₹7,49,217.00 in) |
| Scan/photo OCR | On-device Apple Vision read a generated receipt image (macOS only) |
| Correct a value → dashboard | Income override flows to the dashboard as *confirmed* |
| Loans: options → real cost → compare → what-ifs | EMI ₹9,857.17 and interest ₹54,858.14 for ₹3 L at 11.25 % / 36 m match an independent formula; 48-month EMI ₹7,790.13 matches |
| Missing loan terms | `computable: false` plus a list of what is missing; no invented fee |
| KFS / policy Q&A with page citations | Page-cited facts; "waiting periods" returns the waiting-period fact; off-topic and prompt-injection queries return *not found* |
| Cards: best card for a purchase | Reward maths checked by hand (10 miles per ₹100 × 0.5 ₹/mile); full card numbers rejected |
| EMIs: detect, confirm, calendar, in-app reminders | API + browser |
| Insurance: policy facts, compare, emergency mode | Person-scoped result with citations and non-guarantee wording |
| Upload hardening, encryption at rest, delete-all | Empty / executable / HTML / oversize / traversal / garbage files; stored objects hold no plaintext |
| Security | Cross-user access → 404; login throttling → 429; no account enumeration; foreign Origin → 403; cookie flags and headers |

## WhatsApp channel — verified against a mock gateway only

A local stand-in for the gateway was driven through: a reminder send; `delivered` then `read` receipts (and a late `delivered` not regressing); invalid, missing and wrong-session signatures; an inbound emergency question answered with the right policy and a deep link; duplicate events; unknown senders and group messages (ignored); `STOP` (consent revoked, zero further sends); and a gateway outage (retry scheduled, in-app copy kept). Logs contained no phone number, key or secret.

## Not verified

These need hardware, a paired number or a provider key. Steps are in [`INTEGRATIONS.md`](INTEGRATIONS.md).

| Item | Why |
|---|---|
| Real WhatsApp send / delivery / inbound / `STOP` | Needs a paired dedicated number, Twilio Verify for the phone check, and a public HTTPS webhook URL |
| Gemini chat and function calling | Needs `GEMINI_API_KEY`; adapter is unit-tested with fakes |
| Gemini Live voice | Needs a key and a browser microphone |
| Gemini vision OCR | Needs a key; sends documents to Google |
| Twilio Verify SMS and consultation calls | Needs credentials and a controlled destination number |
| SMTP verification / reset e-mail | Needs SMTP credentials; tested with a fake mailer |
| Camera scanner on a phone | Needs a camera; the route and fallbacks render |
| Screen-reader pass | Manual (VoiceOver / NVDA) |
| Deployment to a public host | Image build and compose are verified locally; no hosted instance exists |

## Known limits

- Loan, card and insurance catalogues are **fictional sample data**, labelled as such. Nothing here is a lender, insurer, broker or adviser.
- WhatsApp uses an *unofficial* gateway suitable for development only (ADR-0002).
- Offline OCR is macOS-only. Login throttling is per process (ADR note in `ratelimit.py`).
- Retrieval is keyword-based, not semantic.
