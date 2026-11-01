# VITRAM: complete project context (for resume tailoring)

Written to be pasted into a Claude project (or any assistant) so it can tailor a resume, cover letter or interview prep for **SDE intern / full-stack
intern** roles at product companies and startups. Every number below was measured or counted in this repository; where something is *not* proven, it says
so. Prefer these facts over inventing new ones.

- **Repository:** https://github.com/pankajbaid567/vitram (single author, `main`)
- **Live demo:** https://vitram.baidpankaj567.workers.dev (press *Open sample workspace*; no sign-up; the first load after idle can take up to a minute on the free tier)
- **Candidate:** Pankaj Baid. Built solo. See "Honest framing" at the end for how to describe the AI assistance accurately.

---

## 1. One-paragraph summary

VITRAM is a full-stack **financial companion for salaried people in India**. Users upload their own bank statements, insurance policies and loan documents;
the system extracts facts with **page-level citations**, builds a financial profile, and then helps with four decisions: **which loan** (ranked options with
the *real* cost, scheduled vs contingent charges), **which credit card to use for a purchase**, **EMIs** (detection, calendar, what-ifs, WhatsApp reminders) and
**insurance** (coverage and exclusions from the policy, plus an "emergency mode" scoped to one family member: "my mother is in hospital, which policy?"). A
tool-grounded assistant (**Vitt Saathi**, English/Hindi/Hinglish) can only narrate numbers computed by deterministic code, and any amount it states that does
not match a tool result to the paise is replaced. It is a decision-support prototype: priced loan/card/insurance data is **fictional sample data**, labelled as such.

## 2. Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, **FastAPI**, SQLAlchemy 2, Pydantic v2, Alembic, httpx; uvicorn |
| Database | **PostgreSQL 16** in production (Neon), SQLite for local/dev; both run the full test suite |
| Frontend | **React 19**, **TypeScript 6**, Vite 8, Tailwind CSS 4, TanStack Query 5, React Router 7, Radix UI, Vitest + Testing Library |
| AI | Google Gemini via `google-genai` (optional, opt-in), deterministic "tool mode" fallback; on-device OCR (Apple Vision) with opt-in cloud OCR |
| Messaging | WhatsApp through a provider port with two adapters: Meta Cloud API (official) and OpenWA/Baileys (unofficial, demo only); Twilio for call/verify |
| Infra ($0 stack) | **Cloudflare Workers** (static app + `/api` proxy + cron + edge rate limiter), **Render** (API, Docker), **Neon** (Postgres), **Cloudflare R2** (S3-compatible encrypted uploads), **Upstash Redis** (rate limits, cache) |
| Observability | Prometheus metrics, OpenTelemetry traces (verified in Jaeger), Grafana dashboard, alert rules, structured JSON logs with request ids |
| Tooling | GitHub Actions CI, k6 (load), Hypothesis (property tests), mutmut (mutation tests), pip-audit / npm audit, axe-core, Docker Compose |

## 3. Scale of the codebase (counted)

| Metric | Value |
|---|---|
| Backend application code | ~13,100 non-blank lines, 108 Python modules |
| Backend tests | ~5,150 lines in 48 files: **656 pass**, 19 conditional skips; **88 % line coverage**; the whole suite also passes on **PostgreSQL (658 tests)** |
| Frontend | ~9,350 lines of TypeScript/React across 59 files; **50 component/journey tests** (render the real route tree against fixtures captured from the live API) |
| API surface | **129 operations on 113 paths**, all documented (`docs/API.md`, generated OpenAPI, checked in CI) |
| Database | **38 tables** (39 with the migration table), **16 Alembic migrations** (apply on empty SQLite and PostgreSQL; roll back to the previous release's revision and forward again with data intact) |
| Documentation | **17 architecture decision records**, 16 docs (architecture, deploy, go-live, performance, observability, security model, releasing, retrieval eval, UX review, status, future) |
| Git | 48 commits, single author |

## 4. Features (what a user can do)

- **Profile from documents:** upload CSV/PDF statements (or a photo; on-device OCR) → income, categories, merchants, recurring payments, review & correct. Duplicate detection by checksum; EXIF stripped; magic-byte checks.
- **Loans:** ranked, reason-coded options; real cost with scheduled vs contingent charges; compare; what-ifs (prepayment, tenure, amount); ask questions of a loan key-facts statement with page citations.
- **Cards:** best card for a purchase using each card's caps, exclusions and reward value; due dates; statement import; reversible reward-cap tracking.
- **EMIs:** detected or manual, month/week calendar, missed-payment and prepayment scenarios, in-app and WhatsApp reminders (consent re-checked at send time; `STOP` wins immediately).
- **Insurance:** coverage, waiting periods and exclusions with sources; plan comparison; **emergency mode** scoped to one family member.
- **Also:** receipts, spending insights, cash-flow forecast, goals, family members, consultation requests, data export (JSON) and full account erasure.
- **Quality of experience:** consistent design system, mobile bottom navigation, honest empty/error states, WCAG-oriented (0 axe violations on 81 route scans), keyboard and touch checks.

## 5. Architecture in brief

```
browser ─► Cloudflare Worker (static app, /api proxy, edge rate limiter, cron keep-awake)
              └─► Render: FastAPI API (+ in-process reminder loop and job loop on the free plan)
                     ├─► Neon PostgreSQL            (data; Row Level Security available)
                     ├─► Cloudflare R2              (encrypted uploads: ciphertext only)
                     ├─► Upstash Redis              (token-bucket rate limits, cache version counters)
                     └─► WhatsApp gateway (OpenWA on Render / Meta Cloud API) ─ signed webhooks ─► Worker ─► API
```

Layering rule: routers (HTTP edge) → services (rules) → pure finance functions. The money maths is **pure, versioned and deterministic**; the assistant can only
narrate tool output. External systems sit behind **ports with adapters** (storage: local/S3; WhatsApp: Meta/OpenWA; OCR: macOS/Gemini/none).

## 6. Engineering highlights, each with evidence

### 6.1 Scale and concurrency
- **Load test (k6)**, one API process + local PostgreSQL: **~213 req/s at saturation with 0 errors**; read p95 **86 ms @10, 108 ms @25, 151 ms @50** concurrent users; sample-workspace creation ~0.45 s locally. (`docs/PERFORMANCE.md`)
- **Profiled and optimised** (cProfile): loan-ranking IRR was a fixed 200-step bisection over an O(n) sum. Early exit + closed-form annuity value: **-46 % CPU per request (13.5 → 7.2 ms), -91 % Python function calls**, equivalence pinned by 400 randomised tests to 1e-12; +14 % saturation throughput of the whole mix.
- **Server-side cache invalidated by data version, not by hand:** per-user version counter bumped by SQLAlchemy `after_commit` on any owned row; keys embed the version and the date; 30 s TTL backstop; Redis-backed so every instance invalidates together. **Dashboard: ~3.5× throughput (85-120 → 325-460 req/s) and ~4× lower p95 (205-320 → 56-78 ms)**; hit = 2-3 queries vs 12-17. Tests cover staleness (new EMI visible on next read), per-user isolation, rollback, Redis outage.
- **N+1 elimination with guardrails:** a query-count test grows a user from 1 to 12 of every item and fails if any read issues more SQL; it found two real N+1s (family list 7 → 29 queries, goals list 5 → 16), both fixed; per-endpoint query budgets for 10 endpoints.
- **Database work:** composite index `(user_id, txn_date, id)` took the newest-100-transactions query from **4.7 ms to ~0.25 ms** (an Incremental Sort became a plain backward index scan, shown with `EXPLAIN ANALYZE`); keyset (cursor) pagination so deep pages cost the same as the first; pool `pre_ping`/recycle for serverless Postgres.
- **Free-tier UX fix:** sample documents are public fixtures, so they are served from the image instead of encrypting/uploading/downloading them for every workspace: **"Open sample workspace" 9-11 s → ~4 s on the free tier (-60 %)**.

### 6.2 Reliability and distributed-systems patterns
- **Durable job queue on PostgreSQL** (ADR-0014): jobs enqueued in the *same transaction* as the upload; claimed with a lease via conditional `UPDATE` + `FOR UPDATE SKIP LOCKED`; exponential back-off with jitter; dead-letter state with a hook that marks the document failed; at-least-once delivery with **idempotent pipeline stages**. A test **spawns a real process that claims a job and is killed (`os._exit`)**, then proves another worker finishes it exactly once; another runs 4 workers over 40 jobs and proves each ran once.
- **Idempotency keys** (Stripe-style middleware): same key + same request replays the stored response; different body → 422; racing duplicate → 409; 10 parallel identical requests have exactly one effect.
- **Optimistic concurrency:** `version` column + `If-Match` (412 with the current version) + database-level `version_id_col` (409). 10 simultaneous edits → exactly one wins.
- **Inbound WhatsApp as durable jobs with a transactional outbox:** the webhook verifies the HMAC signature, records the event, enqueues and acknowledges in one transaction; replies go through a retrying send job. A down gateway delays the reply, never the acknowledgement or the effect.
- **Resilience:** circuit breakers (closed/open/half-open with one probe), bulkheads, retry budget, **load shedding** (503 + `Retry-After` on in-flight and queue-depth limits), fail-open limiter behind its own breaker, chaos-style tests that kill dependencies.
- **Rate limiting:** per-user/per-IP **token buckets** (read 240/min, write 60/min, upload 8/min, assistant 15/min + daily cap) via an atomic **Lua script on Redis**; verified against **real Upstash Redis** (20 racing callers → exactly 5 admitted, state shared across two client instances). An edge limiter in the Cloudflare Worker was **proven live** (limit lowered to 20/10 s: 200 rapid requests → 120 got HTTP 429).

### 6.3 Security
- **Three isolation layers:** (1) owner-scoped queries with a *generated access matrix* that tests every route for 401 (anonymous) and 404 (another user's ids); (2) **PostgreSQL Row Level Security** with per-transaction user context (pooler-safe); (3) user-keyed caches. **The entire backend suite (607 tests) was run as a PostgreSQL role without BYPASSRLS with RLS enforced per request**, which found one real problem (account erasure anonymises audit rows), fixed with an explicit system context. Checked that Neon's default role bypasses RLS and documented the dedicated-role setup.
- **Envelope encryption + key rotation:** per-file random data key wrapped by a master key; rotation re-wraps a ~100-byte header instead of re-encrypting files; legacy blobs upgraded; a 3-key rotation chain, S3 pagination and phone-number lookup hashes (HMAC under the master key) are all tested. Found and fixed a subtle issue: the phone lookup hash would have broken inbound matching after a rotation.
- **Enforcing Content-Security-Policy** (no inline/third-party scripts), rolled out report-only first, then promoted after live-browser journeys showed zero violations; hardening headers on every response; CSRF origin checks; session tokens stored as hashes; redacting log filter.
- **Privacy by design:** consent-first; WhatsApp consent re-checked at send time; export and **complete erasure** (files first, then cascade; tested table by table); R2 holds ciphertext only.
- **Supply chain:** `pip-audit` and `npm audit` in CI (earlier pass found and fixed 73 advisories).
- **Threat model:** STRIDE table mapping each threat to the code and the test that proves it (`docs/SECURITY_MODEL.md`), including an honest "not covered" list.

### 6.4 Testing depth
- **Property-based tests (Hypothesis):** 13 properties × 300 generated cases over the finance engine (schedule clears the loan exactly, balances never rise, closed form == simulation, IRR of a level loan equals its rate, a no-charge prepayment never costs more). **They found a real bug on the first run:** a vanishingly small interest rate made `(1+r)^n − 1` exactly 0 and the EMI divided by zero; fixed with `expm1/log1p` and pinned by a regression test.
- **Mutation testing (mutmut)** on the EMI module: 233 mutants, **78.5 % killed → 89.3 % (208/233)** after writing boundary tests from the survivors; the rest are equivalent mutants.
- **Retrieval evaluation:** 125-question golden set (direct, paraphrase, Hinglish, typo, unanswerable) with a dev/held-out split. BM25 as first measured: **recall@3 61.7 %, paraphrase 33 %, MRR 0.545**. A domain synonym lexicon: **recall@3 85.2 %, paraphrase 73 %, MRR 0.758**, held-out half 87.7 %, abstains correctly on 90 % of unanswerable questions. A hybrid (BM25 + character-trigram TF-IDF with rank fusion) was built and measured as a **statistical tie**, so the simpler BM25 stayed the default (documented as ADR-0017). CI fails if the held-out half regresses.
- **End-to-end in a real browser:** smoke 9/9 and a 16-step new-user journey at desktop and 390 px width, run in CI and against production after each deploy; axe accessibility audit.
- **Other:** migration tests incl. rollback rehearsal; backup-restore proof; route-table-derived access tests; contract tests for the sample data labelling.

### 6.5 Operations and delivery
- **$0 production** on five free tiers, deployed and verified from a real browser (smoke 9/9, journey 16/16 desktop and 16/16 at 390 px) *with the queue, throttle, cache and CSP all live*. Infrastructure as code: `wrangler.jsonc`, a Render Blueprint, a documented Neon/R2/Upstash setup.
- **CI (GitHub Actions):** backend on SQLite and PostgreSQL with a coverage gate, lint, OpenAPI-is-current check, frontend lint/typecheck/test/build, dependency audit, Chrome E2E + accessibility; weekly **backup-restore verification** that compares every table (39 incl. the migration table) by row count and checksum (verified locally: 1,382 rows identical; a deliberately tampered row is detected); PR preview workflow.
- **Zero-downtime migration policy, enforced by a test:** migrations may only *expand* the schema unless they declare a `CONTRACT:` step; rollback to the previous release's revision rehearsed on SQLite (test) and PostgreSQL (by hand, including RLS policies).
- **Observability:** Prometheus RED metrics + queue depth/age + job outcomes + gateway/circuit/cache metrics; `/api/ready` reports DB, migration state and queue health; **OpenTelemetry verified end to end in Jaeger** (one `GET /api/dashboard` = one trace of 21 spans with the request id attached); 8 alert rules; Grafana dashboard JSON; incident-reading guide.

### 6.6 Product and UX
- Honest-by-design: every extracted value carries document, page, snippet and confidence, and can be corrected; unknown terms show "not computable", never an invented fee; missing integrations show "not configured", never a fake success.
- An internal UX audit (dead-button/link crawl: 37 screens, 455 buttons, 832 links, 0 dead links) found and fixed real defects (empty form posted a raw server error; clipped captions; tiny touch targets; watermark text bleeding through). Internal self-rating 86/100; treat it as a self-assessment, not an external score.

## 7. Production deployment (what is live)

| Piece | Where |
|---|---|
| Web app + `/api` proxy + cron + edge limiter | Cloudflare Worker `vitram` (workers.dev) |
| API (+ reminder loop + job loop) | Render free web service (Ohio), Docker |
| Database | Neon free PostgreSQL (us-east-2) |
| Uploads | Cloudflare R2 bucket (ciphertext only) |
| Rate limits / cache state | Upstash Redis (AWS us-east-2, same region as the API) |
| WhatsApp (demo) | OpenWA gateway on Render free; linked device verified `ready`, outbound send verified, inbound webhook delivered |

Known free-tier trade-offs: the API sleeps when idle (a Cloudflare cron pings it every 10 minutes); first request after a long idle can take up to a minute; the sample workspace takes ~4 s.

## 8. Honest limitations (say these before an interviewer finds them)

- **Fictional data and no real users.** All priced products are labelled samples; numbers are from synthetic load on a laptop and a free tier, not production traffic. No claim of users, revenue or uptime.
- **WhatsApp:** the demo gateway (OpenWA/Baileys) uses an unofficial protocol; a number can be restricted. Meta's official Cloud API adapter exists and is tested against a contract, but a live Meta account was **not** exercised.
- **Not done:** MFA, device list/remote sign-out, per-branch API+database previews, multi-instance scaling proof, dense-embedding retrieval, a real data provider.
- Row Level Security needs a non-bypass database role to take effect on Neon (documented with the SQL); it is proven locally, off by default in production.
- The mutation score excludes the rest of the codebase (only the EMI module was mutated); coverage is 88 %, not 100 %.

## 9. Roadmap (what comes next, in priority order)

1. Run with real users for a week (10 testers) to replace synthetic numbers with real p95s and bugs.
2. Per-branch environments (Neon branch DB + throwaway API per pull request).
3. Prove horizontal scale: two API instances against Redis + Postgres, re-run the load test, show cross-instance cache invalidation.
4. Dense retrieval behind the existing seam, only if the golden set shows a gain that justifies sending text to an embedding model.
5. Session security (MFA, device list, rotation on password change).
6. Official WhatsApp (Meta Cloud API) with templates; real catalogue data source.
7. Product depth: SSE for processing progress, PWA/offline dashboard, Hindi navigation labels, empty-state illustrations, a ⌘K shortcut sheet.

## 10. Resume material

### Candidate bullet points (pick 4-6; each is backed by a section above)

**Impact-first (product companies):**
- Built **VITRAM**, a full-stack financial assistant (FastAPI, React/TypeScript, PostgreSQL) that turns a user's bank statements and policies into cited, deterministic loan/card/EMI/insurance decisions; deployed on a $0 stack (Cloudflare, Render, Neon, R2, Upstash).
- Made document processing **crash-safe** with a PostgreSQL job queue (leases, `SKIP LOCKED`, retries, dead-letter); proved exactly-once completion by killing a real worker mid-job in a test.
- Load-tested with k6 (**~213 req/s/process, p95 151 ms at 50 users**); profiled and cut loan-ranking CPU **46 %**, and a version-invalidated Redis-backed cache lifted dashboard throughput **~3.5×** (p95 205-320 → 56-78 ms).
- Removed N+1 queries and added query-count budgets in CI; a composite index plus keyset pagination cut a hot query from **4.7 ms to 0.25 ms**.
- Designed three-layer tenant isolation (query scoping + route-derived access tests + **PostgreSQL Row Level Security**); ran the full suite as a no-bypass role to prove it.

**Correctness and rigor (strong for any company):**
- Wrote Hypothesis property tests and mutation tests (78.5 % → **89.3 %** killed) for the money maths; the property tests **found a real divide-by-zero** on their first run.
- Built a 125-question retrieval golden set with dev/held-out split; lifted recall@3 **61.7 % → 85.2 %** (paraphrase 33 % → 73 %) and added a CI quality gate; measured a hybrid ranker as a tie and kept the simpler design.

**Startup flavour (ownership, breadth):**
- Owned the product end to end: schema and 16 migrations, 129-endpoint API, React UI (0 axe violations), CI/CD, observability (Prometheus, OpenTelemetry, Grafana), security model, and production deployment with a one-command rollback story.
- Added Idempotency-Key and `If-Match` optimistic concurrency so retries and double-clicks cannot double-apply; 10 racing requests → one effect.
- Implemented envelope encryption with zero-downtime master-key rotation, token-bucket rate limiting on Redis (atomic Lua), circuit breakers and load shedding.

### ATS keywords
Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, Docker, REST API design, React, TypeScript, Tailwind, TanStack Query, Vite, Vitest, CI/CD, GitHub Actions, Cloudflare Workers, OpenTelemetry, Prometheus, Grafana, k6, load testing, profiling, query optimisation, indexing, EXPLAIN, caching, rate limiting, token bucket, idempotency, optimistic concurrency, message queue, retries, circuit breaker, Row Level Security, encryption, key rotation, CSP, STRIDE, property-based testing, mutation testing, information retrieval, BM25, LLM grounding, WhatsApp API, accessibility (WCAG).

### Interview talking points (problem → decision → result)
1. **"Documents were lost on restart"** → moved from in-process background tasks to a Postgres job queue with leases → a test that kills a real process shows exactly-once completion. Trade-off: DB polling (5 s) instead of a broker; the `register/enqueue/claim` seam allows swapping.
2. **"Is the cache ever stale?"** → invalidate by per-user data version instead of deleting keys; exclude append-only logs; TTL backstop → tests for staleness, rollback, outage.
3. **"How do you know tenants can't see each other's data?"** → generated access matrix + Row Level Security + user-keyed cache; ran the full suite as a no-bypass role; honest about Neon's `BYPASSRLS` default.
4. **"What did testing find?"** → Hypothesis found the tiny-rate divide-by-zero; N+1 guard found two list endpoints scaling with data; running under RLS found the audit-anonymisation problem; the load test found sample-workspace creation was bound by object-storage round trips.
5. **"Why not embeddings?"** → measured: hybrid tied BM25 on the golden set; dense retrieval would send document text to a model by default; the seam exists if the numbers justify it.
6. **"What would you do at 100× the load?"** → documented in `docs/FUTURE.md`: multi-instance proof, broker instead of DB polling, read replicas/materialised snapshots, per-branch environments.

## 11. Honest framing (important)

- This was built **solo with AI pair-programming assistance (Claude Code)**. On a resume, "built" is fair, but the candidate must be able to explain every design decision, run the tests and load test live, and reproduce the measurements (`loadtest/k6.js`, `python -m evals.retrieval_eval`, `mutmut run`, `scripts/verify_backup.sh`, `docs/PERFORMANCE.md`). If asked directly about AI tools, say so plainly; the verifiable artefacts (tests, benchmarks, ADRs) are the strength.
- Quote numbers with their conditions ("on one process, local PostgreSQL, synthetic load"). Do **not** claim users, revenue, "production traffic", or uptime. Say "deployed on a free tier and verified from a real browser".
- The UX rating (86/100) and "recruiter rating" in `docs/UX_REVIEW.md` are self-assessments.

## 12. Where to look (repo map)

`backend/app/` (routers → services → finance), `backend/app/services/jobs.py` (queue), `idempotency.py`, `concurrency.py`, `throttle.py`, `cache.py`, `resilience.py`, `rls.py`, `security.py` (envelope encryption), `metrics.py`/`tracing.py`; `backend/tests/` (access matrix, jobs crash test, RLS, property and mutation-driven tests); `backend/evals/` (retrieval golden set); `frontend/src/features/*`; `loadtest/k6.js`; `deploy/` (Cloudflare Worker, Render Blueprint, OpenWA wrapper, observability stack, SQL); `.github/workflows/`; `docs/` (start with `ARCHITECTURE.md`, `PERFORMANCE.md`, `SECURITY_MODEL.md`, `STATUS.md`, `DECISIONS.md`).
