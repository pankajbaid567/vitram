# VITTRM completion plan

Status: in progress, 2026-09-23. This plan continues `plan.md`; `checklist.md` is the requirement-by-requirement tracker. The release target is a launch-ready core with all VITTRM journeys. Contract-dependent bank, issuer, lender, insurer and claim-status feeds are later gates; their data remains explicitly sample or user-entered until verified.

## Implementation log (2026-09-23)

- Completed: send-time WhatsApp consent/phone recheck; queued-reminder conversion on STOP, in-app revocation and phone change; conversation-context binding for Live tool calls; paise-accurate model-number guard.
- Completed locally: EMI week view; Twilio Verify v2 phone verification API, UI, rate limits and outbound-contact gate. After the upstream pull, phone verification is migration `0004` (the pulled goals/forecast migration is `0003`). Scanned documents use the pulled Vision layer: on-device OCR by default on supported macOS, explicit `OCR_PROVIDER=gemini` for cloud OCR with consent and low-confidence review.
- Completed: `INTEGRATIONS.md`, `DEMO_SCRIPT.md`, test isolation from local credentials, and locally tested SMTP-backed email verification. The pulled password-reset implementation is retained, with one-time hashed tokens and session revocation. Account-token state is migration `0005`. An earlier accessibility audit found **61 page scans, 0 violations; 8/8 keyboard/touch checks pass**.
- Also completed locally: redacted text-PDF card document upload and page-cited facts, including conservative, individually confirmable purchase rows; sample-only new-card exploration with unknown eligibility. Purchase rows are not auto-applied to a saved card. After this change, backend **104 passed**, frontend **21 passed**, typecheck/build passed and lint had 0 errors (existing warnings). Expanded accessibility audit: **69 page scans, 0 axe violations, 8/8 keyboard/touch checks** immediately before the purchase-row display edit.
- Card-document reconciliation continued: explicit import of confirmed last-four-matched balance/due/reward facts into a selected saved card; per-field provenance in migration `0006`; manual edits supersede the link, while document correction/re-read/deletion clears only imported values. API tests cover ownership, mismatches, overwrite consent and provenance invalidation. A fresh full browser review remains open.
- Pulled `origin/main` to `9740cc4` and merged its M13 Vision, receipts, insights, forecast, goals, scanner and password-reset work with the local changes. The migration chain is `0001`–`0006`; duplicate reset and OCR implementations were consolidated. Combined backend suite **135 passed**, frontend **27 passed**, typecheck and production build passed, lint 0 errors (existing warnings). Expanded browser/a11y checks remain open.
- Fixed a migration-number collision that the pull exposed in the existing local SQLite database: the old branch's `0004` meant phone/email verification, while merged `0004` means phone verification after M13. The upgrade now recognizes the schema, makes an online backup, rebases to `0002`, and conditionally skips already-present verification structures while applying M13 and card import. A disposable regression test passed, and the local dev database reached `0006` with counts unchanged (1 user, 5 documents, 260 transactions, 3 cards).
- Live Gemini checks with only fictional content: text `generateContent` returned successfully; a Gemini Live WebSocket returned audio; app chat used a deterministic tool and returned a tool card; OCR recovered the expected figure from a one-page image-only PDF. These checks do not verify browser microphone/interruption/transcripts, multilingual/safety evaluations or extraction quality on real documents. OpenWA, Twilio Verify/Voice and SMTP delivery have not been tested live.
- Remaining: broader card-statement purchase/category extraction and user-confirmed cycle-spend/reward reconciliation, bounded model extraction for text documents, complete in-app Gemini and OpenWA/Twilio/Verify/SMTP tests, deployment operations and full browser/screen-reader acceptance. See `checklist.md` for the complete gates.
- Owner update (2026-09-23): A paired OpenWA dedicated-number session, a scoped API key, the controlled account's phone-verification gate, and a permanent public HTTPS URL remain pending. The full send/status/inbound/deep-link/STOP/retry sequence has not run.

## 1. Baseline and safety

1. Restore locked backend/frontend dependencies and record fresh test, typecheck, build and migration results on disposable databases.
2. Recheck WhatsApp consent, phone ownership and channel preference at dispatch and retry. In-app and STOP revocation must prevent queued sends while retaining in-app reminders.
3. Bind Live tool calls and transcripts to the authenticated conversation context. Reject cross-user or cross-context requests.
4. Require paise-exact agreement between model money claims and deterministic tool outputs. Audit calculation snapshots, response currency and source contracts.

## 2. Complete the data journeys

1. Add Gemini extraction for scanned PDF pages after AI-processing consent. Persist page evidence and low-confidence review candidates; preserve the explicit no-text recovery path.
2. Add bounded, source-checked model extraction for policy and loan documents. Preserve heuristic facts and user corrections; surface conflicts.
3. Add credit-card statement/benefit-document ingestion with reviewable outstanding, due-date, spend and reward facts. Keep full card numbers and credentials out of storage.
4. Add labelled new-card exploration with transparent eligibility, fees, caps and exclusions. Add an EMI week view consistent with the existing month calendar.

## 3. Verify AI and channels

1. Probe configured Gemini text and Live models with the supplied key without logging secrets. Test real chat function calls, grounding, missing terms, exact amounts and English/Hindi/Hinglish; keep Tool mode as fallback.
2. Test Live microphone, audio, interruption, tools, transcript continuity and reconnect in a browser with a short-lived token.
3. Configure and pair the local OpenWA gateway. Test signed webhooks, delivery statuses, inbound emergency, deep links, duplicate events, STOP and retries.
4. Configure a controlled Twilio consultant destination and current HTTPS callback URL. Test consent preview, bridged call, signed statuses, failure/retry and no recording.

## 4. Account and deployment readiness

1. Use Twilio Verify v2 for phone possession before outbound WhatsApp or saved callback numbers; reverify on number change. Add rate limits and account-visible status.
2. Add password reset and email verification with configurable SMTP, single-use hashed expiring tokens and session revocation. Social login and OTP sign-in remain outside this release.
3. Configure PostgreSQL, HTTPS, secret management, encryption-key rotation, backups/restores, retention/deletion, distributed rate limits and privacy-safe monitoring. Apply Alembic migrations as a backed-up deployment step.
4. Complete screen-reader, phone/desktop, high-contrast and language-metadata checks. Write `INTEGRATIONS.md` and a capability-based `DEMO_SCRIPT.md`; reconcile stale `plan.md` status text.

## Interface changes

- Add card-document upload types and links from extracted facts to saved cards, with extraction method, page evidence, confidence and review state.
- Extend the EMI calendar with week selection while preserving month responses.
- Add phone-verification, password-reset and email-verification endpoints and persisted verification/token state.
- Make AI status distinguish configured settings from a successful provider probe. Preserve honest not-configured and failure states.

## Acceptance and release gates

- Run backend/frontend unit and API tests, typecheck, lint, build, migrations on fresh/upgraded disposable SQLite and PostgreSQL, and the accessibility audit.
- Browser-test the resource document's profile, loan, card, EMI, insurance, emergency and consultation journeys. Test provider outages and consent revocation after scheduling.
- Run controlled, consented live Gemini, OpenWA and Twilio smoke tests. Record provider IDs/status without secrets, financial document text or full phone numbers.
- Rehearse the capability-based demo from a clean sample workspace. Close every applicable `plan.md` requirement ID with implementation and test evidence in `checklist.md`.
- Release first to a restricted pilot. Enable each outbound channel only after credentials, approved template/destination, verified contact, consent, signatures, monitoring and rollback pass.

## Chosen defaults and external inputs

Gemini is the scanned-PDF extraction service with human review. Twilio Verify v2 verifies phones; SMTP sends account email. The configured text and Live model IDs passed narrow provider probes with this key, but complete in-app acceptance is still open. A paired OpenWA session and scoped API key, Twilio consultant number and Verify Service, SMTP credentials, and a stable HTTPS API address are external inputs required for their live gates. No secret values should be pasted into chat.
