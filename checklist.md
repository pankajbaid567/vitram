# VITTRM build and test checklist

Status as of 2026-09-23. Based on `VITRAM_Project_Resource_Document_v1.0.docx` (especially §§27–31), the handwritten ideation page, the current repository, and `plan.md`. Check a box only after the stated evidence exists. `plan.md` records earlier test runs; those are historical results, not a fresh verification of this checkout.

Current verification: `.env` is ignored by Git and has owner-only permissions. After pulling `origin/main` at `9740cc4` and resolving its M13 overlap with local changes, the combined backend suite reached **135 passed**, frontend **27 passed**, typecheck and production build passed, and lint had **0 errors** (existing warnings). The migration chain is now `0001`–`0006` (M13 goals/forecast/reset at `0003`, phone verification at `0004`, account tokens at `0005`, card import at `0006`). An earlier accessibility audit had **69 scans, 0 axe violations, 8/8 keyboard/touch checks** before this merge; the pulled M13 plan reports later scans but a fresh merged audit remains open. Live Gemini text, Live audio-response, function-call chat, and fictional image-PDF OCR probes succeeded in earlier controlled checks; browser microphone/interruption/transcripts, real-document OCR quality, and all OpenWA/Twilio/SMTP delivery remain unverified. Phone verification and account email paths have local mock tests only.

## Pulled M13 scope and merge follow-up

- [x] Preserve the pulled Vision provider layer, receipt scan/review, spending insights, cash-flow forecast, goals, per-item reminder muting, and browser scanner while merging local card, account and channel changes. Backend and frontend automated suites pass after the merge.
- [x] Consolidate duplicate password-reset APIs/UI onto the pulled implementation; keep local email-verification flow and SMTP alias support. Resolve all Git conflict markers and migration revision collisions.
- [x] Re-run frontend production build and lint after the merge: build passed; lint had 0 errors (existing warnings).
- [ ] Re-run the merged accessibility audit, including card import, email verification, receipts, forecast, goals and scanner states.
- [ ] Browser-test the merged document pipeline: scanned statement/policy/loan, receipt photo and transaction linking, redacted card PDF, fact correction/import, reprocess/delete, and source links. On a physical phone, test camera permission, auto-capture, corner adjustment and fallback.
- [x] Detect the pre-pull local `0003`/`0004` migration numbering, back up the SQLite database, then replay the merged chain without adding existing verification fields twice. A disposable regression test passes; the local dev database upgraded from its old `0004` to `0006`, and user/document/transaction/card counts were unchanged (1/5/260/3). The backup is in `backend/.data/backups/`.
- [ ] Verify PostgreSQL upgrade from `0002` to `0006` on a disposable database with backup/restore rehearsal; SQLite migration tests pass.
- [ ] Reconcile older `plan.md` statements about no OCR/email reset with its M13 section and this merged state; historical test counts remain historical.

## Current baseline

- [x] Shared financial profile, statement upload/review, dashboard, family mapping, source-linked loan/policy documents, deterministic loan/card/EMI calculations, and the four journeys are implemented with sample data. See `plan.md` §12 and the corresponding `backend/app` and `frontend/src/features` modules.
- [x] Vitt Saathi Tool mode, scoped tools, citations, English/Hindi/Hinglish responses, and numeric guards have automated coverage. Gemini text, provider-level Live audio response, and a fictional sample-workspace chat with one function-call tool card were verified against the configured provider; complete browser voice and language/safety acceptance remain open.
- [x] In-app reminders, OpenWA adapter/webhook, and Twilio Voice adapter/callback have local/contract tests. External delivery and calling remain unverified.
- [x] Expanded automated accessibility and keyboard checks: 69 scans, zero axe violations, and 8/8 keyboard/touch checks. This does not replace a screen-reader session.
- [x] A repository-root `.env` now maps the supplied Gemini key and model names plus Twilio Voice SID, auth token, and caller number to VITTRM's actual setting names. `.env` is gitignored. VITTRM has no Paytm gateway integration, and the source project's payment/merchant settings do not apply.

## OpenWA integration gates — owner update, 2026-09-23

- [ ] Start the local OpenWA service, pair a dedicated WhatsApp number, and create an operator API key scoped to that session.
- [ ] Finish the controlled test account's phone-verification gate, WhatsApp opt-in and reminder preference. Verify the recipient is the intended test number before any outbound attempt.
- [ ] Confirm VITTRM's permanent public HTTPS API URL and configure the OpenWA `message.received`, `message.ack`, and `message.failed` webhook with the shared HMAC secret.
- [ ] Run and record the complete controlled flow in order: reminder send → delivery callback → inbound emergency/ordinary query → authenticated VITTRM deep link → STOP and no further send → transient failure/retry. Include invalid-signature and duplicate-webhook checks; do not use real medical or financial details in test messages.

## P0 — finish the hackathon MVP

### Build and configuration

- [x] Confirmed `GEMINI_MODEL=gemini-3.5-flash-lite` answered a text probe, `GEMINI_LIVE_MODEL=gemini-3.8-live` returned audio on a harmless Live WebSocket prompt, and the app's chat endpoint used a tool on a fictional sample workspace. This does not establish browser mic or safety acceptance.
- [ ] Complete any fixes revealed by a real Gemini chat run: tool invocation, grounded source references, exact calculator numbers, English/Hindi/Hinglish, unknown terms, error/fallback behaviour, and no unrelated profile data in each journey (§§11, 23, 27.3, 31).
- [ ] Complete any fixes revealed by a real in-app Live voice run: browser mic permission, token, audio input/output, interruption, transcript persistence, tool calls, and recovery after a disconnect (§§11.2, 27.3, 28).
- [ ] Set `OPENWA_BASE_URL`, `OPENWA_API_KEY`, `OPENWA_SESSION_ID`, `OPENWA_WEBHOOK_SECRET`, and this project's `PUBLIC_API_URL`; pair and verify a dedicated test number (§§17, 28, 31.3).
- [ ] Set `CONSULTANT_PHONE_NUMBER` to the team-controlled E.164 destination and `PUBLIC_API_URL` to VITTRM's current HTTPS API URL. Check the supplied Twilio account/caller number permits calls to the intended test numbers. Until then, consultation remains correctly marked “not configured” (§§17.2, 28, 31.4).
- [x] Write `INTEGRATIONS.md` with setup, prerequisites and controlled-test gates; no credential values are included.
- [x] Write `DEMO_SCRIPT.md` following the §30 capability sequence with honest provider states.
- [x] Read image-only statements/policy/loan PDFs through the pulled Vision layer: on-device OCR when available, or explicit Gemini provider with AI consent; extracted values remain lower-confidence and reviewable. Real-document quality and multi-page variation remain to verify (§§9.1, 10, 26, 27.2).
- [x] Recheck WhatsApp eligibility at dispatch and convert queued reminders on in-app/STOP revocation or phone change; local regression tests pass (§§17, 23.1, 26).
- [ ] Review log and failure handling with real integrations enabled: never log API keys, tokens, raw financial documents, full phone numbers or sensitive model context; external errors must leave saved work intact and show a useful retry path (§§23, 26).

### Testing and acceptance

- [x] Run backend suite after the pull on 2026-09-23: `uv run --offline pytest -q` → **135 passed**. Migration tests include fresh/legacy schema, downgrade/upgrade and no-drift; PostgreSQL still needs a fresh run after migrations `0003`–`0006`.
- [ ] Finish frontend verification: fresh `npm test` → 21 passed, typecheck/build passed, lint had 0 errors (existing warnings); expanded axe audit → 69 scans/0 violations and keyboard/touch 8/8. Full browser journeys and live reset/verify delivery still need a fresh run.
- [ ] Browser-test the full profile path with a new user: sign up/consent → upload a real text PDF or CSV statement → review/correct income, categories and recurring items → dashboard/profile reflect corrections. Test multiple accounts, overlapping files, duplicates, a 3/6/12-month selection, optional salary, and source links (§§9, 27.4, 31.1).
- [ ] Browser-test Loans: purpose/amount/tenure/collateral → personalized catalogue options and reasons → compare at least two → Real Cost separates scheduled fees/interest from contingent charges → what-if uses deterministic figures → uploaded KFS question opens the correct source page (§§12, 27.4, 31.2).
- [ ] Browser-test Cards with at least two saved cards and representative spends: correct best-card ranking, benefit rules, caps/exclusions, reward currency valuation, unknown balances, and card last-four masking (§§13, 27.1, 27.4, 31.3).
- [ ] Browser-test EMIs: detected or manual obligation → confirm/reject → correct calendar due date → late/missed/prepayment what-if, including “charge unknown” when terms are absent; verify in-app reminder and opt-out (§§14, 27.4, 31.3).
- [ ] Perform a consented OpenWA test with a controlled recipient: reminder sends, delivery status webhook updates it, inbound emergency question routes correctly, duplicate webhooks are safe, invalid signature is refused, and STOP prevents further sends (§§17, 27.4, 31.3).
- [ ] Browser-test Insurance: upload a policy → review/correct coverage, exclusions and waiting periods → ask a sourced policy question → compare labelled sample plans → select an affected family member and event → receive a relevant policy and grounded claim-document checklist; unknown claim terms remain unknown (§§15–16, 27.4, 31.4).
- [ ] Perform a consented Twilio test to controlled numbers: show the exact summary and destination before requesting, create one outbound call, verify consultant bridge and no recording, process signed status callbacks through completion/failure, and test invalid signatures/retry (§§17.2, 27.4, 31.4).
- [ ] Run an actual screen-reader pass (VoiceOver or NVDA) on sign-in, upload/review, dashboard, Saathi chat/voice, calculator, calendar, emergency flow, and modal focus/announcements; recheck 375–390 px and desktop layout (§24, `plan.md` §11).
- [ ] Rehearse §30 from a clean/seeded environment and capture evidence for every §31 acceptance item. Verify the demo still works when Gemini, WhatsApp or Twilio is unreachable, with truthful “unavailable/not configured” states (§§26, 29–31).

## P1 — full specification beyond the required MVP

- [ ] Finish card-document intelligence: redacted text-PDF upload extracts last-four, due date, amount due, points and explicitly labelled purchase rows with source pages; detected full PAN/CVV/PIN is rejected. A user can now confirm the last four and individual balance/due/reward facts, select a matching saved card, explicitly replace values, and view the source. Ownership, mismatch, overwrite, reprocess and deletion cases have API tests; only imported fields are cleared on source loss. Purchase rows remain low-confidence, individually confirmable facts and do **not** enter cycle-spend/rewards automatically. Still add robust issuer-layout coverage and correction/rejection plus category/reward reconciliation for purchase rows (§§9.1, 13.1).
- [x] Ship optional sample-only new-card exploration: fees, category rules/caps, exclusions, user-spend matches, unknown eligibility and source freshness are shown without a ranking across incompatible reward currencies or an apply handoff.
- [ ] Broaden document fixtures to scanned/low-quality files, password-protected/damaged PDFs, conflicting versions, prompt-injection text, and real bank/policy/KFS layout variations. Test page citation and extraction confidence/review (§§10, 26, 27.2).
- [ ] Validate production deployment settings before any public launch: data encryption key, DB backup/restore, auth/consent, user-scoped access, retention/deletion, HTTPS/webhook URLs, catalogue freshness, monitoring and regulator/partner review (§§23, 26, 32). Do not present fictional catalogues as live products.
- [ ] Defer issuer reward balance feeds, lender/insurer quote or purchase handoffs, continuous bank sync, claim-status integrations, advisor routing/CRM and granular family accounts until their partners and consent models exist (§28). Test each against its actual contract when implemented.

## Plan requirement coverage audit

`[x]` here means the repository contains the feature and `plan.md` records local tests. It does **not** mean a fresh test was run for this audit or that an external service worked. Every `[ ]` is a remaining build, decision, or verification task. IDs are the complete set from `plan.md` §2; historical claims in §4 are reconciled below.

### Platform, onboarding, and profile

- [x] **P1** — VITTRM and one Vitt Saathi identity across journeys (`SaathiPanel`, AI router).
- [x] **P2** — INR display and Indian grouping in UI/backend; check currency/precision in the fresh contract run below.
- [x] **P3** — Standalone account flow with no Paytm authentication dependency.
- [x] **P4** — Common dashboard linking the four journeys.
- [x] **P5** — Loans/Insurance as pillars, Cards/EMIs as supporting journeys.
- [x] **P6** — Salaried individual scope, with no merchant workflow.
- [x] **P7** — Responsive shell and journey layouts; historical screenshots cover phone/tablet/desktop.
- [x] **O1** — Sign-in, sessions, terms and purpose-based consent records.
- [x] **O2** — Basic salaried-person onboarding, with optional personal details.
- [x] **O3** — Salary remains optional.
- [x] **O4** — Family member CRUD and explicit policy-member association.
- [x] **O5** — WhatsApp and call consent controls exist; live channel gates still need testing.
- [x] **F1** — 3/6/12-month CSV/text-PDF upload, bank-account labels and multi-account data model.
- [x] **F2** — Persisted processing stages and retry UI.
- [x] **F3** — Salary/other-income candidate detection and confirmation.
- [x] **F4** — Expense category rules with an Other fallback.
- [x] **F5** — Frequent-merchant counts and spend.
- [x] **F6** — Recurring obligation detection.
- [x] **F7** — Cash-flow, fixed/variable spend, surplus and volatility fields.
- [x] **F8** — Neutral behaviour summaries and high-value events with references.
- [x] **F9** — Potential EMI/card detections with user confirmation.
- [x] **F10** — Structured financial profile plus normalized records.
- [x] **F11** — Review, correction and user override precedence.
- [x] **F12** — Extracted/confirmed/conflicted/missing fact states.
- [x] **F13** — Persisted extracted facts/profile reused by Saathi tools.
- [x] **F14** — Duplicate-file and overlapping-transaction detection.
- [x] **F15** — Image-only PDFs/photos use on-device OCR by default where supported, or explicitly configured Gemini OCR with AI consent; facts carry lower confidence and require review. No available provider yields a recovery error. Provider accuracy remains an open live-test gate.
- [x] **F16** — Multiple salary candidates require confirmation.
- [x] **F17** — Ambiguous merchants are correctable from Other.

### Documents and Vitt Saathi

- [x] **D1** — Extracted facts hold document/page/section/snippet/confidence and correction state; verify timestamps/source links across all fact types in the fresh contract run.
- [x] **D2** — Text-layer insurance policy extraction, structured facts and page references.
- [x] **D3** — Text-layer loan/KFS extraction, terms, fees and clauses.
- [ ] **D2/D3 AI path** — `plan.md` §4/§7 describes optional Gemini structured extraction, but `pipeline.py` calls only heuristic extractors. Implement and verify a bounded, source-checked model path if it remains a promised feature; remove the claim from the plan otherwise.
- [ ] **D4** — Card documents can be uploaded, scanned for credentials, extracted and corrected with page citations; reviewed balance/due/reward facts can be explicitly imported into a last-four-matching saved card with source tracking. Narrow purchase-row extraction exists, but robust merchant/category parsing and confirmed cycle-spend/reward reconciliation remain open.
- [x] **D5** — Scoped document search, sourced answers and an explicit not-found path; test conflict wording and source opening in the browser.
- [x] **D6** — Document list, facts, corrections, reprocess and delete.
- [x] **D7** — Conflicting policy versions are preserved and flagged by tested code.
- [x] **D8** — Injection-looking PDF text is excluded from structured facts; repeat with new fixtures and live model path.
- [x] **A1** — One assistant with context-specific tool allow-lists.
- [x] **A2** — Global and module-specific chat entry points.
- [ ] **A3** — A provider-level Gemini Live WebSocket returned audio with this key. Complete microphone/audio playback, interruption, transcripts and tool calls in a real browser; the app token and browser path are not yet verified end to end.
- [ ] **A4** — Verify that voice and text actually resume the same conversation and retain the proper context after a page change/reconnect.
- [ ] **A5** — Tool-mode English/Hindi/Hinglish has tests; verify real Gemini text and voice in all three, including rupee figures and script labels.
- [ ] **A6** — One real Gemini function-call turn produced a deterministic tool card on a fictional workspace. Still verify source/terms affordances, multiple turns, module tool scopes and failure recovery; Tool mode and adapter mocks exist.
- [ ] **A7** — Paise-exact numeric guard and wrong-amount regression tests now pass; evaluate false claims, missing fees, scope and family privacy with live responses before closing.
- [x] **A8** — Structured tool cards and citation affordances.
- [x] **A9** — Desktop panel, mobile sheet and voice-state UI; real voice states remain under A3.
- [x] **A10** — Labelled Tool mode and graceful fallback on AI failure.
- [ ] **A11** — Context allow-list tests exist; inspect actual requests from each live Gemini and Live voice context to confirm data minimization, masking and family isolation.

### Loans and cards

- [x] **L1** — Dashboard/Saathi/Explore/document loan entry points.
- [x] **L2** — Purpose, amount, tenure, collateral, comfort and profile context in intake.
- [x] **L3** — Versioned fictional catalogue with source/date/mock label.
- [x] **L4** — Eligibility/unknown handling, ranking and reason codes.
- [x] **L5** — Deterministic Real Cost with scheduled and contingent components; recheck representative hand-calculated examples.
- [x] **L6** — Multi-product comparison.
- [x] **L7** — Source-backed clause severity/warnings.
- [x] **L8** — Amount/tenure/prepayment/missed/rate what-if calculations.
- [x] **L9** — KFS document analysis and sourced Q&A for text PDFs; OCR gap is F15.
- [x] **L10** — No live lender application handoff or implied approval.
- [x] **C1** — Manual card entry and last-four-only storage; document input remains D4.
- [x] **C2** — Card detail with manually entered due, balance and reward information.
- [x] **C3** — Deterministic best-card ranking with rule/cap/exclusion data.
- [x] **C4** — Rewards, redemption and category insights; check missing/expired valuation rules in the fresh journey test.
- [x] **C5** — Sample-only new-card exploration is built/tested; it shows spend relevance but explicitly marks eligibility unknown and does not rank unlike reward currencies or claim an issuer offer.
- [x] **C6** — Two or more saved cards can be ranked for a purchase.

### EMI, insurance, and channels

- [x] **E1** — Statement-detected, manual and loan-document EMIs with confirmation.
- [x] **E2** — EMI terms/source fields and editing.
- [x] **E3** — Month/week calendar API and UI are implemented with a cross-month API regression test; browser parity still needs checking.
- [ ] **E4** — Cadence, consent and in-app delivery exist; configure OpenWA and verify a real send, callback and privacy-safe preview.
- [x] **E5** — Missed/late/prepayment/rate/new-EMI scenarios; unknown charges stay non-computable.
- [x] **E6** — New EMI comparison, saved terms/charges and refinance link.
- [x] **E7** — No invented consumer credit score or score-impact claims in current UI; recheck generated answers.
- [x] **I1** — Insurance overview, policy/family coverage, explore, consult and emergency routes.
- [x] **I2** — Upload → extract → member mapping → correction/confirmation flow.
- [x] **I3** — Coverage, exclusions, waiting periods, claims and source links for text PDFs.
- [x] **I4** — Family/profile-aware recommendations from a labelled catalogue.
- [x] **I5** — Insurance comparison of cover, limits, cost, restrictions and claims.
- [ ] **I6** — Consent/context preview and Twilio request lifecycle exist; set consultant/public URL and verify a real call and callbacks.
- [x] **I7** — Person-scoped emergency shortlist and sourced claim guidance; live voice/WhatsApp variants remain A3/W1.
- [x] **I8** — Claim non-guarantee copy exists; recheck real model responses.
- [ ] **I9** — Renewal scheduling and local WhatsApp emergency routing exist; verify real sends/replies and deep links.
- [ ] **W1** — OpenWA adapter, signatures, STOP and idempotency have local tests; queued-send revocation and Twilio Verify phone gate are now built/tested. Pair a dedicated session, configure its key/webhook/public URL and run controlled send/inbound/status/retry tests.
- [ ] **W2** — Twilio adapter, consent and signed callback have local tests; verify real call creation, bridge, status, failure/retry and no recording.
- [x] **W3** — Twilio is confined to consultation; in-app voice uses Gemini Live.
- [x] **N1** — In-app notifications for document processing, obligations and failures; verify noise/dedup behaviour with real scheduling.

### Security, contracts, quality, and demo

- [x] **S1** — Purpose/per-call consent and send-time WhatsApp recheck are implemented; queued sends convert to in-app on revocation or phone change, with regression coverage.
- [x] **S2** — Card last-four-only forms and server validation; no CVV/PIN/bank-password field.
- [ ] **S3** — Encrypted upload files/private download exist. Validate HTTPS, secure-cookie/proxy settings, encryption-key management and database/disk encryption in the intended deployment; no deployment is shown here.
- [x] **S4** — User-scoped document and other object queries with cross-user tests; repeat for new endpoints.
- [x] **S5** — Delete document/family/all-my-data UI and routes; verify cascade and backup-retention policy in deployment.
- [x] **S6** — Audit events for access/corrections/calculations/outbound actions; inspect real integration logs for sensitive data.
- [ ] **S7** — CalculationRun snapshots/versions exist and Live tool context mismatch now returns 409 with a regression test; audit every calculation route and live prompt masking before closing.
- [x] **S8** — Prototype and sample-product labels exist; review all externally visible claims before release.
- [ ] **Q1** — Run response-contract audit across routes for INR/precision, reason codes, missing flags, citations, catalogue date/mock labels and calculation inputs/outputs/version. The plan's proposed `Money{amount,currency}` contract differs from its later per-payload-currency assumption.
- [ ] **Q2** — Fresh unit/API/component/e2e run plus extraction, live AI and live channel evaluations as listed above; historical M12 results are 92 backend and 21 frontend tests, not the older 76/6 shown in §12.
- [ ] **Q3** — Write and rehearse the capability-based demo script against a seeded workspace, with evidence for §31 acceptance.
- [x] **Q4** — Catalogue metadata includes source/date/mock/staleness; check stale-copy behaviour in browser.

### Plan and release bookkeeping

- [x] **Roadmap M1–M5** — Foundation, profile data, dashboard, finance engine and Tool-mode Saathi have implementation and historical local tests. Real Gemini acceptance for M5 remains under A5–A7.
- [x] **Roadmap M6–M9** — Loan, insurance, card and EMI local journeys have implementation and historical tests. Full acceptance still depends on OCR, WhatsApp, consultation and the tests above.
- [ ] **Roadmap M10** — Complete the live voice and channel acceptance criteria; token/webhook adapters alone do not satisfy the “works when credentials provided” gate.
- [ ] **Roadmap M11** — Finish the original polish/demo milestone: current responsive/a11y/sample work is reported complete, while the demo script and fresh full journey rehearsal are open. Later UI work also uses the name M11; disambiguate in `plan.md`.
- [ ] Update `plan.md` header, §4 statuses, §7 integration note, §10 assumptions and §12 summary once the next test pass is done. Current text still says no credentials, no automated axe audit, Tool mode only answers in English, and no Alembic migration tool, even though later M10–M12 entries supersede those claims. Fix the M10/M11 milestone-name collision and replace the old 76/6 totals with dated results.
- [ ] Separate **implemented**, **historically tested**, **freshly tested**, and **verified against a live provider** in the plan. A populated `.env` proves only that values were supplied; it does not prove model access, template approval, phone verification, delivery or a call.
- [ ] Complete `INTEGRATIONS.md` and `DEMO_SCRIPT.md`, then link them from README and the plan. Keep the local secrets out of tracked files.
- [ ] Audit §11 Definition of Done for each journey: persistence, provenance, validation, four UI states, mobile/desktop, accessibility, consent/authz, unit/API/browser evidence, and updated tracker. Record any unmet item rather than marking its parent feature fully done.
- [ ] Resolve account flows before production: password reset and email/phone verification are now built with local mocks, but require SMTP/Twilio Verify live delivery tests. OTP sign-in, social login and email change remain unbuilt and optional; keep unavailable options honestly labelled.
- [ ] Review the M11/M12 visual notes on real devices: Windows high-contrast mode, Devanagari/Hinglish `lang` on user messages, and the background image's visible “YOUR MONEY · A BRIGHTER YOU” text behind wide-screen content. Theme switching remains optional.
- [ ] Ask the owner which qualities of “AAge Saathi” are intended for Vitt Saathi, then record a product-specific voice/tone acceptance check without copying another product's branding or design (§10.4).

## Environment mapping and open inputs

| Source setting | VITTRM setting | State |
| --- | --- | --- |
| `GOOGLE_API_KEY` | `GEMINI_API_KEY` | Copied into gitignored `.env`; text, app-chat and fictional PDF OCR probes passed |
| `GAWAAH_LLM_MODEL` | `GEMINI_MODEL` | Copied; `generateContent` text/OCR probes passed |
| `GAWAAH_LIVE_MODEL` | `GEMINI_LIVE_MODEL` | Copied; provider-level audio response passed, browser Live flow unverified |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | Same names | Copied; calls stay disabled without consultant number |
| Local `OpenWA/` gateway | `OPENWA_*` | Pair a dedicated session and issue a scoped API key |
| Source Cloudflare tunnel | `PUBLIC_API_URL` | Left blank because it belongs to the other project and may be expired |
| Paytm/Razorpay gateway, GAWAAH shop/data settings | None | Outside VITTRM scope |

The supplied credentials appeared in the conversation. Keep `.env` local and rotate/reissue those credentials before any shared or public deployment.
