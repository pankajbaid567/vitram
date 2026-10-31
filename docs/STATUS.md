# Verification status

What has actually been run, and what has not. Last full pass: **2026-11-01** (macOS; Linux containers; SQLite and PostgreSQL 16; Chrome headless).
"Verified" means observed working, not merely implemented. Anything that needs a phone, a provider key or a hosting account is listed
under *Not verified* rather than claimed; [`GO_LIVE.md`](GO_LIVE.md) is the order to verify it.

## Automated checks

| Check | Result | Command |
|---|---|---|
| Backend tests | **517 pass**, 10 documented skips (routes that address shared catalogue data) | `make test-backend` |
| Backend coverage | **88 %** (8.6k statements) | `cd backend && uv run pytest -q --cov=app` |
| Backend on a Linux container | pass (same results as macOS) | `make ci-linux` |
| Backend on PostgreSQL 16 | pass, including four racing workers and the shared rate limiter (migration tests are SQLite-specific) | `TEST_DATABASE_URL=postgresql+psycopg://… uv run pytest -q --deselect tests/test_migrations.py` |
| Backend lint | clean | `uv run ruff check .` |
| Frontend tests | **48 pass** (journeys render the real route tree against fixtures captured from the live API) | `make test-frontend` |
| Typecheck, lint, build | pass; lint has **0 warnings** | `make lint && npm run build` |
| Migrations | `0001 → 0010` apply on empty SQLite and PostgreSQL; `0007` also verified on PostgreSQL with data; idempotent for pre-Alembic databases | `python -m app.migrate upgrade` |
| Browser end to end | **9/9 steps** on the local stack **and** on the containerised stack (nginx → API → PostgreSQL + worker); proven to fail on the original Documents crash | `make e2e` |
| Accessibility | **0 axe violations** (81 route scans; 79 on the Linux stack, which has no on-device OCR), 8/8 keyboard and touch checks. Screen-reader testing is still manual | `make a11y` |
| Dependency audit | `pip-audit` and `npm audit`: **no known vulnerabilities** (this found and fixed 73 in Pillow, pypdf, aiohttp, pyasn1, pyjwt and certifi) | `make audit` |
| API reference | `docs/API.md` + `openapi.json` current (129 operations), checked in CI on Linux | `uv run python scripts/export_openapi.py --check` |
| Container stack | `docker compose up`: PostgreSQL, API (migrates on start), **separate worker**, nginx. `/api/ready` shows the worker's heartbeat; the doctor runs inside it | `make up` |
| Backup and restore | PostgreSQL + uploads backed up and restored into a new database: 63 users, 2,178 transactions, 722 facts, 59 documents all matched, same schema revision; refuses without `--yes` | `backend/scripts/backup.sh`, `restore.sh` |
| CI | green on GitHub: backend (SQLite + PostgreSQL), audit, frontend, browser e2e + accessibility | `.github/workflows/ci.yml` |

## Journeys observed working end to end

| Journey | Evidence |
|---|---|
| Sign-up, login, logout, session; data export; account deletion | API + browser; deletion proven across every user table and every stored file, audit trail anonymised |
| Statement upload (CSV, text-PDF) → profile | 260-row CSV parsed; totals reconcile to the paisa against an independent recomputation (₹6,98,163.14 out, ₹7,49,217.00 in); a 2-year statement (~1,080 rows) processes in ~0.2 s |
| Scan/photo OCR | On-device Apple Vision read a generated receipt image (macOS only; opt-in test `pytest -m real_ocr`) |
| Correct a value → dashboard | Income override flows to the dashboard as *confirmed* |
| Loans: options → real cost → compare → what-ifs | EMI ₹9,857.17 and interest ₹54,858.14 for ₹3 L at 11.25 % / 36 m match an independent formula; 48-month EMI ₹7,790.13 matches; every calculator returns a stored `calculation_id` |
| Missing loan terms | `computable: false` plus what's missing; no invented fee |
| KFS / policy Q&A with page citations | Page-cited facts; "waiting periods" returns the waiting-period fact; off-topic and prompt-injection queries return *not found* |
| Cards: best card; statement purchases → rewards | Reward maths checked by hand; confirmed purchases move a monthly cap (₹8,000 already spent reduces the miles left on a ₹48,000 purchase), reversibly |
| EMIs, in-app reminders | API + browser |
| Insurance: facts, compare, emergency mode | Person-scoped result with citations and non-guarantee wording |
| AI-assisted extraction (opt-in) | Against a *fake model*: grounded values kept, 12 kinds of ungrounded or hostile proposal rejected, deterministic facts never overwritten, provider failure falls back |
| Upload hardening, encryption at rest | Empty / executable / HTML / oversize / traversal / garbage files; stored objects hold no plaintext |
| Security | Every one of the API's routes rejects an anonymous caller or is on the justified public list; every object route returns 404 to a different user; login throttling; foreign Origin → 403; cookie flags and headers; unexpected errors return a request id and no internals |

## WhatsApp, Twilio, Gemini: verified against mocks only

| Provider | What was exercised |
|---|---|
| **Meta Cloud API adapter** | Request shapes (template with three sanitised variables; free-text replies), `X-Hub-Signature-256`, the `GET` verification handshake, message/status/button/interactive parsing, wrong-number payloads dropped, error mapping (retryable vs. final), the token never appearing in an error |
| **OpenWA adapter** | The same scenarios through one shared test suite |
| Both, through the webhook route | Invalid/missing signature, replays ignored, unknown senders and groups ignored, `STOP` revokes consent and stops sends, the delivery ladder never regresses, outage → retry with the in-app copy kept |
| Twilio | Call request shape (no recording, escaped TwiML), failure mapping, the verified-phone gate, retry, cancel, signed status callbacks, replays |
| Gemini | Tool loop bounded, unknown tools refused, cooldown after failure, numeric-fidelity replacement, ephemeral voice tokens never expose the API key, the insurance prompt carries no banking data |
| `python -m app.doctor` | Each probe against mocked responses; secrets never in the output, even when a provider echoes one |

## Not verified

These need hardware, a paired number, a provider key or a hosting account. [`GO_LIVE.md`](GO_LIVE.md) gives the order and the expected result of each.

| Item | Why |
|---|---|
| Real WhatsApp send / delivery / inbound / `STOP` (Meta or OpenWA) | Needs a verified business and approved template (Meta) or a paired spare number (OpenWA), plus a public HTTPS webhook URL |
| Gemini chat, languages, function calling, Live voice, vision OCR | Needs a key (and a microphone for voice); adapter tested with fakes |
| Twilio Verify SMS and consultation calls | Needs credentials and a controlled number |
| SMTP verification / reset e-mail | Needs credentials; tested with a fake mailer |
| Camera scanner on a phone; screen-reader pass | Needs a camera / assistive technology |
| Render and Fly.io blueprints (`deploy/`) | Configuration only; the container images and compose stack they are based on *are* verified |
| A hosted instance | None exists |

## Known limits

- All *priced* catalogue data is **fictional sample data**; the real-institution card and insurance lists are **reference-only** (name, official link, verification date; no fees or benefits). Both are labelled and a contract test enforces it. Nothing here is a lender, insurer, broker or adviser.
- WhatsApp via OpenWA is unofficial (ban risk): development only. Production uses the Meta adapter, which needs an approved template.
- Uploads are stored on local disk (encrypted), so run one API instance until an object-storage adapter exists.
- Offline OCR is macOS-only; elsewhere scans need the opt-in Gemini provider or return a clear "can't read scans here".
- Rate limiting is per process unless `RATE_LIMIT_BACKEND=database`. There is no key-rotation tooling for `VITRAM_DATA_KEY`.
- Retrieval is keyword-based, not semantic.
