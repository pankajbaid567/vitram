# VITRAM

[![CI](https://github.com/pankajbaid567/vitram/actions/workflows/ci.yml/badge.svg)](https://github.com/pankajbaid567/vitram/actions/workflows/ci.yml)

An AI-assisted financial companion for salaried people in India: **loans, cards, EMIs and insurance** from one financial profile built out of your own bank statements and documents, with **Vitt Saathi (वित्त साथी)** as the single assistant.

> The app's on-screen brand is **VITTRM**; VITRAM is the project name.
> **Decision-support prototype.** All *priced* loan, card and insurance data is fictional sample data, labelled as such. The lists of real cards and insurance products are **reference-only** (names and official links, with no fees or benefits invented). VITRAM is not a lender, insurer, broker or adviser.

| | |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.jpg) | ![Loan options with real cost](docs/screenshots/loan-options.jpg) |
| ![Which card to use](docs/screenshots/card-optimizer.jpg) | ![Emergency mode, scoped to one family member](docs/screenshots/emergency-mode.jpg) |

## What makes it different

- **Numbers you can trust.** EMI, real cost (scheduled vs contingent charges), prepayment, missed-payment and reward maths are pure, versioned functions, verified against independent recomputation. The assistant can only *narrate* their output; an amount in a model reply that doesn't match a tool result to the paise is replaced. Unknown terms give "not computable", never an invented fee.
- **Every fact opens its source.** Values extracted from statements, policies and loan documents carry document, page, snippet and confidence, and can be corrected by the user.
- **Consent where it matters.** Outbound WhatsApp is re-checked against consent and a verified phone *at send time*; `STOP` wins immediately.
- **Honest about what it can't do.** Missing integrations show *not configured*, never a fake success. See [`docs/STATUS.md`](docs/STATUS.md) for exactly what has and hasn't been verified.

## Journeys

| Journey | What you get |
|---|---|
| **Profile** | Upload a CSV/PDF statement (or a photo of one) → income, categories, merchants, recurring payments, review & correct |
| **Loans** | Ranked, reason-coded options → real cost → compare → what-ifs; ask questions of a loan key-facts document with page citations |
| **Cards** | Best card for a purchase using each card's caps, exclusions and reward value; due dates; card-document import |
| **EMIs** | Detected or manual EMIs, month/week calendar, missed-payment and prepayment scenarios, in-app and WhatsApp reminders |
| **Insurance** | Policy documents → coverage, exclusions, waiting periods with sources; compare plans; **Emergency mode** scoped to one person |
| **Also** | Receipts, spending insights, cash-flow forecast, goals, family members, consultation requests |

## Run it

**Local (SQLite, no keys needed).** Python ≥ 3.11 with [uv](https://docs.astral.sh/uv/), Node ≥ 20.

```bash
# backend → http://127.0.0.1:8000
cd backend && uv sync --extra ai && uv run uvicorn app.main:app --port 8000

# frontend → http://localhost:5173 (proxies /api to the backend)
cd frontend && npm install && npm run dev      # port 8000 busy? API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
```

Open <http://localhost:5173> and choose **Open sample workspace** (generated fictional documents processed through the real pipeline), or create an account.

**Full stack in containers (PostgreSQL + API + nginx).**

```bash
cp .env.example .env     # then set VITRAM_DATA_KEY (command in the file)
docker compose up --build        # → http://localhost:8080   (WEB_PORT to change)
```

## Tests and quality gates

```bash
cd backend  && uv run pytest -q --cov=app     # 177 tests, 84 % coverage
            && uv run ruff check .
cd frontend && npm test && npm run typecheck && npm run lint && npm run build     # 31 tests
```

CI runs the backend on SQLite *and* PostgreSQL and the frontend on every push. Details and results: [`docs/STATUS.md`](docs/STATUS.md).

## Database

SQLite (`backend/.data/vitram.db`) by default; set `DATABASE_URL` for PostgreSQL (`uv sync --extra postgres`). **Alembic** owns the schema (`backend/migrations`, `0001 → 0008`). Pending migrations apply at start-up (`AUTO_MIGRATE=true`) and an existing SQLite file is backed up first; in production set `AUTO_MIGRATE=false` and run `uv run alembic upgrade head` as a deploy step after a backup.

```bash
uv run python -m app.migrate status | backup | upgrade | restore <file>
uv run alembic revision --autogenerate -m "…"     # review before committing
```

## Integrations

All optional; configure through `.env` (see [`.env.example`](.env.example)).

| Integration | Enables | State |
|---|---|---|
| Gemini | Free-form assistant, consented scan OCR, live voice | Adapter unit-tested; live use unverified. Without it the assistant runs in labelled *Tool mode* |
| WhatsApp (OpenWA gateway) | EMI/card/renewal reminders, emergency quick-query, `STOP` | Verified against a mock gateway. **Unofficial gateway: dev/demo only**, see [ADR-0002](docs/DECISIONS.md) |
| Twilio Verify / Voice | Phone possession check; insurance consultation calls | Gated and tested locally; no live SMS or call run |
| SMTP | E-mail verification and password reset | Tested with a fake mailer |
| Apple Vision (macOS) | On-device OCR for photos and scans | Verified on macOS |

Setup and the live-test checklist: [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md).

## Documentation

| | |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layers, money path, document pipeline, channels, security model, failure behaviour, scaling path |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Architecture decision records |
| [`docs/STATUS.md`](docs/STATUS.md) | What is verified, how, and what is not |
| [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) · [`docs/DEMO.md`](docs/DEMO.md) | Provider setup · demo walkthrough |
| [`docs/spec/`](docs/spec) | Product requirements document, ideation page, historical plan |

## Layout

```
backend/    FastAPI · SQLAlchemy · Alembic · finance engine · document pipeline · Saathi · channels
frontend/   React 19 · TypeScript · Vite · Tailwind v4 · Radix
docs/       architecture, decisions, status, integrations, demo, spec
.github/    CI
```
