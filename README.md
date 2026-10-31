# VITTRM

AI-powered financial journeys for salaried professionals in India — Loans, Insurance, Credit Cards and EMIs, with
**Vitt Saathi (वित्त साथी)** as the single assistant. Built from `VITRAM_Project_Resource_Document_v1.0.docx` and the
handwritten ideation page; see [`plan.md`](plan.md) for requirements and [`plan2.md`](plan2.md) / [`checklist.md`](checklist.md) for completion work.

> Decision-support prototype. Loan, card and insurance catalogues are **sample data with fictional institutions**.
> VITTRM is not a lender, insurer, broker or adviser.

## Run it locally

Requirements: Python ≥ 3.11 with [uv](https://docs.astral.sh/uv/), Node ≥ 20.

```bash
# backend (http://127.0.0.1:8000)
cd backend
uv sync --extra ai            # --extra ai installs google-genai (needed only when Gemini is configured)
uv run uvicorn app.main:app --reload --port 8000

# frontend (http://localhost:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and either create an account or choose **Open sample workspace** — a separate, clearly
labelled account whose generated sample documents (6-month bank statement, three policies, a loan KFS) are processed
through the real pipeline.

## Tests

```bash
cd backend && uv run pytest -q          # finance engine, parsing, extraction, journeys, Saathi, channels, migrations
# optional: run the suite on PostgreSQL → TEST_DATABASE_URL=postgresql+psycopg://… uv run pytest -q --deselect tests/test_migrations.py
cd frontend && npm test && npm run typecheck && npm run build
```

Sample documents are generated deterministically: `cd backend && uv run python scripts/make_fixtures.py`.

## Database & migrations

SQLite (`backend/.data/vitram.db`) is the default; set `DATABASE_URL` for PostgreSQL
(`uv sync --extra postgres` installs the driver, e.g. `postgresql+psycopg://user:pass@host/vitram`).
The schema is managed by **Alembic** (`backend/migrations/`).

- **Start-up**: pending migrations are applied automatically (`AUTO_MIGRATE=true`, default). A database created before
  migrations existed is detected, stamped with the matching revision without any schema change, then upgraded.
- **Backups**: before any migration touches an existing SQLite file, a consistent copy is written to
  `backend/.data/backups/vitram-<timestamp>-pre-<revision>.db` (SQLite online-backup API, safe while the app runs).
  For PostgreSQL, take a `pg_dump` before upgrading — VITTRM logs a reminder but cannot do it for you.
- Commands (from `backend/`):

  ```bash
  uv run python -m app.migrate status            # current vs head revision
  uv run python -m app.migrate backup            # manual SQLite backup
  uv run python -m app.migrate upgrade           # apply pending migrations (with backup)
  uv run python -m app.migrate restore <backup>  # restore a SQLite backup (stop the API first; the current file is backed up too)
  uv run alembic revision --autogenerate -m "…"  # new migration after changing app/models.py — review it before committing
  uv run alembic downgrade -1                    # manual only; never run automatically
  ```
- Production: set `AUTO_MIGRATE=false` and run `uv run alembic upgrade head` as a deploy step after a backup.

## Document vision & intelligence (M13)

- **Photos and scans**: JPG, PNG and WebP photos and scanned PDFs are read by OCR (see Integrations). Photos are rotated upright, downscaled and re-encoded before storage, which removes EXIF metadata such as GPS location. HEIC isn't accepted (phones convert to JPG on upload).
- **Live camera scanner**: "Scan with camera" opens an in-browser scanner built on OpenCV.js (`@techstark/opencv-js`, Apache-2.0). It finds the page's edges in real time, captures automatically when the phone is steady, lets you adjust the corners, straightens the page and offers Enhanced / Colour / Black & white looks. Everything runs in the browser, and only the final scan is uploaded. Camera access needs HTTPS or `localhost`; without a camera the upload box offers the phone camera app or a file instead.
- **Receipts** (`/documents/receipts/new`): merchant, date, total, GST lines, items and payment method, each with its source line. Nothing is confirmed automatically; long digit runs (card numbers) are cut to the last 4. Matching to a bank transaction is a suggestion the user chooses; no transaction is created.
- **Review** any document's values (confirm / correct / reject) in Documents & data; rejected values are never used. Vitt Saathi can summarise or search one document (`document` context).
- **Spending insights** (`/insights`), **cash-flow estimate** (`/forecast`) and **goals** (`/goals`) use only the user's own, confirmed or entered data; see `plan.md` M13 for the rules.

## Screens & accounts

- `/login`, `/signup` (and `/welcome`, an alias of sign-up). Signed-out visitors are sent to `/login` and returned to the page they asked for; a session that ends mid-use shows a "session ended" notice.
- `/profile` — personal details, Vitt Saathi reply language, contact permissions, password change (`POST /api/auth/password`; signs out other devices) and the confirmed financial profile.
- Phone possession verification uses Twilio Verify v2 when configured; until a number is verified, outbound WhatsApp and live consultation calls are gated. Email verification and single-use password-reset links use configured SMTP; without SMTP, the UI reports that delivery is unavailable. OTP sign-in and social login are not implemented.
- App background: `frontend/src/assets/app-background.jpg` (from `resources/`), shown on signed-in and onboarding screens only.

## Integrations

Copy `.env.example` to `.env`. Nothing below is required to run the app; each missing integration shows an honest
"not configured" state.

| Integration | Enables | Settings | Status in this repo |
|---|---|---|---|
| Gemini | Free-form Vitt Saathi chat with function calling and consented scanned-PDF OCR | `GEMINI_API_KEY`, `GEMINI_MODEL` | Text, one sample-workspace tool call and fictional image-PDF OCR passed live provider probes; full language/safety and real-document evaluation remain open. Without it, chat runs in labelled **Tool mode**. |
| Gemini Live | In-app real-time voice (ephemeral token → browser) | `GEMINI_API_KEY`, `GEMINI_LIVE_MODEL` | A provider-level WebSocket returned audio; browser microphone, interruption, transcripts and tool calls are **not yet verified**. |
| OpenWA | EMI/card/renewal reminders, emergency quick-query, STOP opt-out | `OPENWA_*`, `PUBLIC_API_URL` | Self-hosted send and signed-webhook contracts are tested locally; a paired live session is still required. Reminders always appear in-app. |
| OCR — Apple Vision (default on macOS) | Photos and scanned PDFs: receipts, policies, loan documents, statements | `OCR_PROVIDER=auto` (default) | **Verified on this Mac**: a Swift helper (`backend/tools/ocr_macos.swift`) is compiled on first use into `backend/.data/bin/`; documents are read on-device. Needs Xcode command-line tools (`swiftc`). |
| OCR — Gemini vision (opt-in) | Same, on servers without Apple Vision | `OCR_PROVIDER=gemini`, `GEMINI_API_KEY`, `GEMINI_VISION_MODEL` (or `GEMINI_MODEL`) | Built against `google-genai` 2.25 (`Part.from_bytes` + `response_json_schema`), contract-tested offline; **not verified live**. Sends documents to Google — never chosen automatically. |
| SMTP email | Email verification and password-reset links | `SMTP_HOST`, `SMTP_FROM` (+ `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_PORT`, `SMTP_STARTTLS`, `APP_ORIGIN`) | Both flows tested with a fake mailer; **no live email sent**. Not configured → reset is shown as unavailable. |
| Twilio Voice | Insurance consultation calls | `TWILIO_*`, `CONSULTANT_PHONE_NUMBER`, `PUBLIC_API_URL` | Call creation + signed status webhook built and tested locally; **no live call verified**. Requests are saved with "no call was placed". |
| Twilio Verify | SMS phone possession check before outbound contact | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID` | API and gating locally tested; **no live SMS verified**. |

See [`INTEGRATIONS.md`](INTEGRATIONS.md) for safe setup and live-test gates, and [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) for the capability-based walkthrough.

OpenWA webhook URL: `{PUBLIC_API_URL}/api/webhooks/openwa` (HMAC secret = `OPENWA_WEBHOOK_SECRET`).
Twilio status callback: `{PUBLIC_API_URL}/api/webhooks/twilio`.

## Layout

```
backend/   FastAPI · SQLAlchemy · deterministic finance engine · document pipeline · Vitt Saathi orchestrator
frontend/  React · TypeScript · Vite · Tailwind v4 · Radix primitives
plan.md    requirements, traceability matrix, design system, architecture, roadmap, progress tracker
plan2.md   completion roadmap; checklist.md tracks open implementation and test work
```
# paytm-mumbai
