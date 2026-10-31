# VITTRM — Implementation Plan

> **Historical design record.** Written before and during the build; kept for its requirement IDs (P1, O1, F1 …, cited in code and tests) and design rationale.
> It is **not** a status report: current verification state is in [`docs/STATUS.md`](../STATUS.md), architecture in [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md), and decisions in [`docs/DECISIONS.md`](../DECISIONS.md). Older test totals and "no credentials" statements below are superseded.
> **Correction:** where this plan says the WhatsApp channel is "per RD §17.1", note the RD locks the *official Meta WhatsApp Cloud API*; the self-hosted OpenWA gateway is a later implementation choice (see ADR-0002).

**Source documents read in full**

| ID | Document | How it was read |
|----|----------|-----------------|
| **RD** | `spec/VITRAM_Project_Resource_Document_v1.0.docx` — Project Resource Document + PRS, v1.0 (35 sections + Appendices A–C, 2 figures) | Converted with pandoc; both embedded figures (Fig. 1 Document-to-Profile Pipeline, Fig. 2 Reference Architecture) inspected as images. |
| **HW** | `spec/ideation-page.jpeg` — handwritten ideation page | Inspected visually, then cropped and upscaled per region for accurate transcription (see §1.4). |

Section references below use `RD §n` and `HW:<area>`.

**Source-of-truth order:** (1) owner's explicit decisions/corrections → (2) RD → (3) HW → (4) engineering judgment for unspecified implementation details only. RD states it "solidifies the project owner's handwritten ideation and subsequent decisions", so where HW and RD differ in detail, RD wins (none of the differences found are true conflicts — see §10.3).

---

## 1. Product Understanding

### 1.1 What VITTRM is
VITTRM is a **standalone, India-only, AI-powered financial journeys platform** for **formal-sector salaried individuals / young professionals** (RD §2, §4, §6.1). It turns a user's own financial data and documents — bank statements, insurance policies, loan and card documents, onboarding answers — into a **reusable, structured, correctable Financial Profile** with **source-linked facts**, and uses that foundation to make **Loans, Credit Cards, EMIs and Insurance** understandable, personalized and actionable (RD §2.1, Appendix C).

Core loop (RD §2.2): **DATA → STRUCTURE → UNDERSTANDING → PERSONALIZATION → CALCULATION → EXPLANATION → ACTION**, delivered across Web + Voice + WhatsApp + Consultation Call.

### 1.2 Who it's for
- Primary: salaried, formal-sector, India-based; not assumed financially sophisticated (RD §6.1).
- Individual-first account with a **lightweight family layer** for coverage, dependants and obligations (RD §6.2).
- Explicitly **not**: business owners/merchants; Paytm-login dependent; persona-story demo (RD §3.3, §33.1).

### 1.3 Scope and experience
- **Two core pillars:** Loan Journey and Insurance Journey (RD §4, HW: "Loan Part" / "Insurance Part").
- **Supporting intelligence:** Credit Card Intelligence and EMI Intelligence (RD §4, HW).
- **One AI identity — Vitt Saathi (वित्त साथी)** — chat + real-time voice, context/tools scoped per page (RD §11).
- **Channels:** self-hosted OpenWA (reminders, emergency quick-query, linked Q&A) and Twilio (insurance consultation calls) (RD §17.1 specifies Meta's Cloud API — see ADR-0002).
- **Principle that makes it VITTRM, not a chatbot:** language intelligence is separated from financial truth. Numbers come from deterministic code; product/document facts come from catalogues and source-linked extractions; the LLM explains and orchestrates (RD §1, §2, §5, §22).
- **Honest prototyping:** curated/mock catalogues are allowed but must be labelled; nothing claims to be live unless it is (RD §4, §5).

### 1.4 Handwritten ideation (HW) — transcription
Top: "Mumbai" → branches to **Loan Part** and **Insurance Part**.

- **Loan Part** — "Vitt Saathi AI" ("AAge saathi jaisa bana dena" — *make it like "AAge Saathi"*), Purpose of loan?, "Kya girvi rakhna?" (*what collateral to pledge?*), Real cost of loan, Loan Comparison, Personalized loan recommendation, clause/warnings, hyper-personalization.
- **Centre (shared profile)** — Personal info + Bank Statement → Extract info such as income, expenses etc. → Existing insurance bond PDF upload → Extract info.
- **Insurance Part** — Personalized insurance recommendation (Health, Term life, Others — LIC); "build AAge Saathi-like AI" + Insurance Consultation Call; personalization from data. **Post Insurance Feature**: WhatsApp chat during medical emergency — user can ask about existing insurance (like AAge Saathi), clause, requirements etc., also which one to use.
- **Credit Card Intelligence System** — Card management & associated benefits; AI assistant — points, miles, redemption; Which card should I use for purchase?; Airline, hotel, tickets; Maximise rewards on spending; hyper-personalization based on expenses.
- **EMI Intelligence** — EMI management + Smart Calendar + notification on WhatsApp; AI intelligence → Comparisons, clauses, hidden charges?, What if? — "Sab kuch AI assistant bata de" (*the AI assistant explains everything*). Chatbot + Speaking AI ("AAge Saathi").
- Bottom (struck through by author): "EMI Statement Intelligence AI" — **treated as removed**.

"AAge Saathi" is an external reference the owner used for the *feel* of the assistant. RD does not define it; we do not copy any third-party branding/design (see §10.4 Q1).

---

## 2. Source-of-Truth Requirements

IDs are used in the traceability matrix (§4). **L** = locked decision (RD §1.1/§4), **D** = implementation default in RD, **HW** = also present in handwritten notes.

### 2.1 Platform & identity
| ID | Requirement | Source |
|----|-------------|--------|
| P1 | Product name VITTRM; AI identity Vitt Saathi (one assistant everywhere) | L — RD §4, §11.1; HW |
| P2 | India only; INR everywhere | L — RD §4, §20.1 |
| P3 | Standalone app; no Paytm auth/ecosystem dependency | L — RD §3.3, §4, §33.1 |
| P4 | All journeys begin from a common dashboard | L — RD §4, §8.2, §31.1 |
| P5 | Loans + Insurance are core pillars; Cards + EMI are supporting | L — RD §4; HW |
| P6 | Not for business owners; not a budgeting/social app | L — RD §3.3 |
| P7 | Mobile-responsive-first modern web app | D — RD §18.1 |

### 2.2 Onboarding, family, profile
| ID | Requirement | Source |
|----|-------------|--------|
| O1 | Register/sign-in + purpose-based consent to data processing | RD §7.2, §23.1 |
| O2 | Onboarding: name, contact per auth, terms; age/DOB; employment = salaried path; optional city/employer/designation/salary | RD §8.1, S02 |
| O3 | Salary optional; never forced | L — RD §4, §33.1 |
| O4 | Family: add member (name/nickname, relation, age/DOB); optional; explicit whose-data | RD §6.2, S03, S51 |
| O5 | Channel opt-in: WhatsApp reminders/support; consultation-call consent | RD §8.1 |
| F1 | Bank statement upload: 3/6/12 months; PDF and/or CSV; multiple accounts (demo one primary) | L — RD §4, §9.1, S04; HW |
| F2 | Processing progress: upload → parse → categorize → profile; retry | RD S05, §18.1 async jobs |
| F3 | Income detection (salary, recurring, irregular, consistency) | RD §9.2; HW |
| F4 | Expense categories (food/delivery, e-commerce, travel, utilities, rent, education, healthcare, entertainment, subscriptions, transfers, other) | RD §9.2; HW |
| F5 | Merchant intelligence: frequent merchants, monthly frequency and spend | RD §9.2 |
| F6 | Recurring obligations: EMIs, card bills, rent, premiums, subscriptions, repeating transfers | RD §9.2 |
| F7 | Cash-flow metrics: avg inflow/outflow, fixed vs variable, surplus/deficit, volatility | RD §9.2 |
| F8 | Behaviour summaries in neutral language; high-value events with source ref | RD §9.2 |
| F9 | Potential EMI/card-payment detection; user confirms/corrects | RD §9.2, §14.1 |
| F10 | FinancialProfile structure (identity…review_state) persisted as structured JSON + normalized tables | D — RD §9.3, §19 |
| F11 | Review & correction screen; corrections stored as user-verified overrides that win over future AI guesses | L — RD §4, §9.4, S06 |
| F12 | Fact states: Extracted / User confirmed / Conflicted / Missing, with specified behaviour | RD §9.4 |
| F13 | Extract once; don't repeatedly send raw docs to the model | L — RD §4, §33.1 |
| F14 | Dedup: checksum duplicate uploads; overlapping statement transaction fingerprint | RD §26 |
| F15 | Password-protected PDF → explain + ask for unlocked export; scanned PDF → low confidence + verify | RD §26 |
| F16 | Multiple salary-like credits → show for confirmation, don't assume | RD §26 |
| F17 | Ambiguous merchant → Other/Uncategorized + correctable | RD §26 |

### 2.3 Documents & traceability
| ID | Requirement | Source |
|----|-------------|--------|
| D1 | Every document-derived fact keeps provenance: document id, page/section, snippet, confidence, timestamp, user_verified | L — RD §4, §10, §19.1 |
| D2 | Insurance extraction schema (identity, people, financials, coverage, restrictions, claims, provenance) | RD §10.1; HW |
| D3 | Loan document extraction schema (core terms, fees, late/default, security, repayment, clauses, provenance) | RD §10.2 |
| D4 | Credit-card document extraction (outstanding, due date, merchant spend, rewards) where practical | RD §9.1, §13.1 |
| D5 | Grounded Q&A: scope to the document; short quotes; "not found" instead of inference; "View source"; surface conflicts | RD §10.3 |
| D6 | Documents & Data screen: list, status, delete, reprocess, extracted facts | RD S50, §7.1, §20 |
| D7 | Conflicting policy PDFs → keep both versions, surface conflict | RD §26 |
| D8 | Prompt-injection text in PDFs treated as content only | RD §23.3, §27.2 |

### 2.4 Vitt Saathi
| ID | Requirement | Source |
|----|-------------|--------|
| A1 | One identity; per-context package + tool permissions (dashboard, loan, card, EMI, insurance, emergency) | L — RD §11.1 |
| A2 | Chat panel on every major module + global access from dashboard | RD §11.2 |
| A3 | Real-time voice via Gemini Live; model id configuration-driven; interruptible; transcripts shown | L — RD §4, §11.2, §33; HW "Chatbot + Speaking AI" |
| A4 | Voice and chat share session context where practical | RD §11.2 |
| A5 | English, Hindi, Hinglish | RD §11.2, App. B |
| A6 | Tool-first orchestration (intent → fetch → deterministic tool → explain → "View terms") | RD §11.3, §18.2 |
| A7 | Safety rules: never invent rates/fees/benefits/exclusions/rewards/deadlines; no LLM arithmetic; fact vs education; "why this may fit"; state missing data; family privacy; stay in module | L — RD §11.4, App. B |
| A8 | Tool outputs render as structured cards; source affordance on every sourced statement | RD §24.1 |
| A9 | Desktop right-side panel; mobile full-height sheet; one-tap voice with listening/speaking state | RD §24.1 |
| A10 | LLM unavailable → dashboards/calculators still work, graceful assistant-unavailable state | RD §26 |
| A11 | Privacy by purpose: only the needed profile slice enters each context | RD §5, §27.3 |

### 2.5 Loans
| ID | Requirement | Source |
|----|-------------|--------|
| L1 | Entry points: Dashboard → Loans; Saathi "I need a loan for…"; Explore Loans; Upload loan doc → Analyze | RD §12.1 |
| L2 | Intake: purpose (required), amount (required), tenure (optional), collateral ("kya girvi rakhna?") where relevant, EMI comfort, obligations and income from profile (overridable) | RD §12.2; HW |
| L3 | Curated catalogue with identity, eligibility, pricing, repayment, docs, source + last_updated + mock/live | L — RD §4, §12.3 |
| L4 | Recommendation: hard eligibility filters, unknown ≠ fail, transparent fit features, configurable weights, reason codes, "why this may fit" | RD §12.4, §21.1–21.2; HW |
| L5 | Real Cost: principal, interest, processing fee, GST on fees, doc/legal/valuation charges, bundled insurance, other charges, prepayment/foreclosure conditions, contingent late/penal separately, scheduled total outflow, annualized cost if computable | L — RD §5, §12.5, §22.2; HW |
| L6 | Comparison of ≥2 products: price, flexibility, eligibility fit, collateral, warnings, why-it-fits, source freshness | RD §12.6, §31.2; HW |
| L7 | Clauses & warnings with severity labels (Important, Cost impact, Flexibility impact, Eligibility/condition); never invented | RD §12.7; HW |
| L8 | What-if: tenure, amount, prepayment, missed/delayed EMI, floating-rate change, alternatives (baseline vs scenario) | RD §12.8, §22.3 |
| L9 | Loan document analyzer: upload → extract with page refs → "Loan at a glance" → Real Cost → clauses with View source → scoped Q&A | RD §12.9, S16 |
| L10 | "Apply" is placeholder only if permitted; no real application handoff | RD S14, §23.2 |

### 2.6 Credit cards
| ID | Requirement | Source |
|----|-------------|--------|
| C1 | Add card manually or by statement/benefit doc where practical; masked id only; never full PAN/CVV/PIN | RD §13.1, §23.1 |
| C2 | Card detail: issuer/name, masked id, limit, outstanding, due date, annual fee, benefits, reward currency, points/miles, expiry, redemption options | RD §13.1, S21; HW |
| C3 | "Which card should I use?" — deterministic rules, caps, exclusions, milestones; ordered result with expected reward, why, caveat | RD §13.2, §21.4; HW |
| C4 | Rewards: don't equate currencies without valuation rule; travel/hotel/voucher/statement credit paths; expiring points; better-card-for-category from spending | RD §13.3; HW "Airline, hotel, tickets", "maximise rewards" |
| C5 | New-card exploration optional (deferred) | RD §13.3, §33 |
| C6 | ≥2 cards can be compared for a purchase | RD §31.3 |

### 2.7 EMIs
| ID | Requirement | Source |
|----|-------------|--------|
| E1 | Sources: auto-detect from statements, manual add/edit, import from loan docs, confirm uncertain | RD §14.1; HW |
| E2 | EMI record fields (name/type, lender, principal?, EMI, due day, remaining tenure, rate/terms, late rule, source) | RD §14.2 |
| E3 | Smart calendar (month/week) incl. card/premium obligations | RD §14.3; HW |
| E4 | WhatsApp reminders via OpenWA after opt-in; configurable cadence (demo: days-before + due-date); minimal sensitive data in previews | L — RD §14.3, §25; HW |
| E5 | What-if: missed, one-month-late, part-prepayment (reduce tenure or EMI), rate change, new-EMI affordability; never fabricate charges | RD §14.4, §22.3, §31.3; HW "What if?" |
| E6 | EMI comparisons/clauses/hidden charges explained by Saathi (HW); exploration via Loans refinance path is "optional later" | HW; RD §12.1 |
| E7 | No unsupported credit-score impact claims | Owner prompt; RD §8.2 (no invented score) |

### 2.8 Insurance & emergency
| ID | Requirement | Source |
|----|-------------|--------|
| I1 | Insurance home: existing policies by type/person, explore, coverage overview, family coverage, consultation, emergency | RD §15.1 |
| I2 | Policy upload flow: select covered person(s) or confirm later → upload → extract → review/correct → available to Saathi and emergency | RD §15.2; HW |
| I3 | Policy summary: coverage, premium, exclusions, waiting periods, claims, source links, correction | RD S42, §10.1 |
| I4 | Explore/recommend with family, financial, existing-coverage, intent (health, term life, others e.g. LIC-type traditional, travel) + labelled catalogue | RD §15.3, §21.3; HW |
| I5 | Compare: coverage, cost (non-binding label), waiting/co-pay/deductible/sub-limits, family fit, claims, why, source | RD §15.4 |
| I6 | Consultation via Twilio: topic + callback number + consent → consented context summary → call → status; no default recording | L — RD §15.5, §17.2; HW |
| I7 | Emergency mode: affected person → event → only that person's policies → applicable shortlist (no certainty) → coverage/conditions/cashless vs reimbursement/documents/contacts → View source → chat/voice | RD §16; HW "Post Insurance Feature" |
| I8 | Never guarantee claim approval | L — RD §33.1 |
| I9 | WhatsApp: quick entry into emergency/claim assistance; renewal reminders | RD §17.1, §25; HW |

### 2.9 Channels, security, notifications, quality
| ID | Requirement | Source |
|----|-------------|--------|
| W1 | Self-hosted OpenWA; reminders, renewals, emergency quick query, linked Q&A, deep links, signed webhooks (inbound, status, opt-out), idempotent retry | L — RD §17.1, §26 |
| W2 | Twilio Programmable Voice for consultation; consent + minimal record; status webhook; failure → show failed + retry, never imply call happened | L — RD §17.2, §26 |
| W3 | Twilio not used for in-app voice (Gemini Live does that) | RD §17.2 |
| N1 | Notifications: EMI, card payment, renewal, document processed, needs-review (in-app, avoid noise) | RD §25 |
| S1 | Purpose-based consent for documents, WhatsApp, calls | RD §23.1 |
| S2 | Data minimization; no card credentials/CVV/PIN/banking passwords | RD §23.1 |
| S3 | Encryption in transit and at rest; private storage via backend proxy | RD §23.1 |
| S4 | Object-level authorization | RD §23.1 |
| S5 | User-visible delete controls | RD §23.1 |
| S6 | Audit events: document access, corrections, recommendations, outbound comms | RD §23.1 |
| S7 | Masked identifiers in prompts; no calculation persisted without input snapshot + formula version | RD §23.3 |
| S8 | Regulatory boundary: decision-support prototype; labelled catalogues; not a lender/insurer/broker | RD §23.2 |
| Q1 | Every money value INR + precision; recommendations return reason codes + missing flags; facts return citations; catalogue returns source/last_updated/mock flag; calculations return inputs/outputs/formula version | RD §20.1 |
| Q2 | Unit tests per RD §27.1; extraction fixtures per §27.2; AI evals §27.3; E2E §27.4 | RD §27 |
| Q3 | Capability-based (not persona) demo with seeded data | L — RD §3.3, §30 |
| Q4 | Stale catalogue → show last updated, avoid "current" claims | RD §26 |

---

## 3. Feature and Module Breakdown

### 3.1 Modules
| Module | Features | Screens (RD §24 ids) |
|--------|----------|----------------------|
| **Access & Onboarding** | Sign up / sign in, consent, About You, Family setup, Bank statement upload, Processing, Profile review | S01–S06 |
| **Dashboard** | Saathi Ask/Speak, 4 journey cards, income/spend/obligations/surplus, upcoming obligations, coverage summary, card snapshot, data-quality indicator, quick upload | S07 |
| **Financial Profile Engine** | Statement parsing (CSV, text PDF), dedup, categorization, merchant/recurring detection, cash-flow metrics, overrides, fact states | S05, S06, S50 |
| **Document Intelligence** | Upload/store (encrypted), extraction (policy/loan/card), facts + citations, grounded search, reprocess, delete | S16, S41, S42, S50 |
| **Vitt Saathi** | Chat orchestrator, context packages, tools, source/tool cards, voice (Gemini Live), offline tool mode | S08 + panel on every module |
| **Loans** | Home, need intake, results, comparison, detail/Real Cost, what-if, document analyzer | S10–S16 |
| **Credit Cards** | Home, add card, card detail, spend optimizer, rewards/redemption | S20–S22 |
| **EMIs** | Home + totals, calendar, detail, add/edit/confirm, what-if, reminder settings | S30–S33 |
| **Insurance** | Home, policy upload, policy summary, explore, results, comparison, consultation, emergency mode | S40–S47 |
| **Family** | Members, policy-member mapping | S03, S51 |
| **Channels** | WhatsApp send/webhook/opt-out; Twilio call/webhook; reminder scheduler | S33, S46 |

### 3.2 Primary user journeys (from RD §7.2, §27.4, §30)
1. **Profile once:** Sign up → consent → About You → (Family) → upload statement → processing → review & correct → dashboard.
2. **Loan:** Dashboard / Saathi "loan for X" → intake (purpose, amount, tenure, collateral, EMI comfort) → results with reasons → compare 2–3 → detail with Real Cost + clauses → what-if.
3. **Loan document:** Upload KFS/sanction → at-a-glance + Real Cost + clauses (View source) → ask Saathi about the document.
4. **Card:** Add ≥2 cards → "Which card for ₹30,000 flight?" → ordered result with reward, why, caveat.
5. **EMI:** Detected EMI confirmed / manual EMI → calendar → reminder opt-in → WhatsApp reminder → what-if (missed/prepay).
6. **Insurance:** Upload policy (select member) → structured summary + sources → ask grounded question → explore/compare labelled catalogue → consult (Twilio).
7. **Emergency:** Emergency mode → member + event → applicable policies → claim steps + documents + contacts → chat/voice.

### 3.3 Secondary journeys
Add/edit family members; correct a transaction category or recurring label; delete/reprocess a document; opt out of WhatsApp (in-app or "STOP"); retry a failed consultation call; change reminder cadence.

---

## 4. Requirements Traceability Matrix

Status values: **Not started · In progress · Implemented · Tested · Blocked (reason)**. "Tested" means automated tests and/or a verified run through the running app. It never means only that a screen exists.

| Req | Requirement | Source | Planned implementation | Status |
|-----|-------------|--------|------------------------|--------|
| P1 | One Vitt Saathi identity | RD §4, §11 | Single `VittSaathi` orchestrator + single UI component; context passed as parameter | Tested |
| P2 | INR everywhere | RD §20.1 | `Money` schema `{amount, currency:"INR"}`; paise-precision rounding helper; `formatINR` (Indian grouping) in UI | Tested |
| P3 | Standalone, no Paytm | RD §3.3 | Local email+password auth | Tested |
| P4 | Common dashboard entry | RD §4 | `/` dashboard route; all module links from it | Tested |
| P5/P6 | Pillars/scope | RD §4 | Nav order: Home, Loans, Insurance, Cards, EMIs; no unrelated modules | Tested |
| P7 | Mobile-first responsive | RD §18.1 | Tailwind breakpoints; bottom nav on mobile | Tested (375/390 px + 1440 px screenshots) |
| O1 | Auth + consent | RD §7.2, §23.1 | `/auth/*`, `consents` table (purpose, granted_at, revoked_at), consent step in signup | Tested |
| O2/O3 | Onboarding fields, optional salary | RD §8.1 | S02 form; salary field explicitly optional with explanation | Tested |
| O4 | Family members | RD §6.2 | `family_members` CRUD, S03/S51 | Tested |
| O5 | Channel opt-in | RD §8.1 | Consents `whatsapp_reminders`, `consultation_calls` + phone | Tested |
| F1 | Statement upload 3/6/12, multi-account | RD §9.1 | `POST /documents` type `bank_statement` + account label + period; `bank_accounts` table | Tested (CSV + text PDF; multi-account schema) |
| F2 | Processing progress | RD S05 | Background job with stage field polled by UI | Tested |
| F3–F9 | Transaction intelligence | RD §9.2 | `statement_parser` + `categorizer` + `recurring` + `profile_engine` modules | Tested |
| F10 | Profile structure | RD §9.3 | `financial_profiles.profile_json` versioned + normalized tables | Tested |
| F11/F12 | Review/correction + states | RD §9.4 | `profile_overrides`, per-fact `state`, S06 | Tested |
| F13 | Extract once | RD §4 | Facts persisted; Saathi reads facts/chunks, never raw files | Tested |
| F14 | Dedup | RD §26 | SHA-256 checksum check; txn fingerprint unique per account | Tested |
| F15 | Encrypted/scanned PDFs | RD §26 | pypdf encryption detection → explicit error; no text layer → low-confidence/failed state with guidance | Tested |
| F16/F17 | Salary ambiguity, uncategorized | RD §26 | `salary_candidates[]` needing confirmation; "Other" category | Tested |
| D1 | Provenance | RD §10, §19.1 | `document_facts` with page/section/snippet/confidence/user_verified; `SourceCitation` schema | Tested |
| D2 | Insurance extraction | RD §10.1 | `extractors/insurance.py` (heuristic, text PDF) + optional Gemini structured extraction with snippet verification | Tested |
| D3 | Loan doc extraction | RD §10.2 | `extractors/loan.py` same pattern | Tested |
| D4 | Card doc extraction | RD §13.1 | Deferred to after core; manual add first | Not started (manual card add ships instead, per assumption 15) |
| D5 | Grounded Q&A | RD §10.3 | `document_chunks` (page-level paragraphs) + keyword retrieval scoped to doc; "not found" path | Tested |
| D6 | Documents & Data | RD S50 | `/documents` list, delete (cascades derived data), reprocess | Tested |
| D7 | Conflicts | RD §26 | Fact comparison across docs for same policy number → `conflicted` state | Tested |
| D8 | Prompt injection | RD §23.3 | Document text wrapped as untrusted data; system prompt rule; fixture test | Tested |
| A1/A11 | Context packages | RD §11.1 | `context.py` builds minimal slice per context; tool allow-list per context | Tested |
| A2/A9 | Chat UI everywhere | RD §11.2, §24.1 | `SaathiPanel` (desktop right panel / mobile sheet) in app shell | Tested (desktop panel + mobile sheet) |
| A3/A4 | Gemini Live voice | RD §11.2 | Backend mints short-lived token (`POST /ai/session-token`); browser connects with `@google/genai`; tool calls proxied to backend; transcripts appended to same conversation | Blocked (needs GEMINI_API_KEY + GEMINI_LIVE_MODEL) — token endpoint + browser client built, not verified live |
| A5 | En/Hi/Hinglish | RD §11.2 | System prompt; IBM Plex Sans Devanagari font; offline router matches Hinglish keywords | Implemented (Gemini prompt + Hinglish keyword routing; Tool-mode replies are English) |
| A6/A7 | Tool-first + safety | RD §11.3–11.4 | Gemini function calling over deterministic tools; numeric-fidelity guard (narrative numbers must appear in tool output) | Tested (Tool mode + offline Gemini contract tests) |
| A8 | Structured tool cards | RD §24.1 | Tool results returned as typed `cards[]` rendered by UI | Tested |
| A10 | LLM unavailable | RD §26 | Labelled "tool mode": intent router → same tools → templated answer | Tested |
| L1–L2 | Loan intake | RD §12.1–12.2 | S10/S11 form + Saathi `loans.search` | Tested |
| L3 | Loan catalogue | RD §12.3 | `catalogues/loans.json` — fictional lenders, `is_mock:true`, `last_updated` | Tested |
| L4 | Recommendation | RD §12.4, §21 | `recommend/loans.py` filters + features + weights config + reason codes | Tested |
| L5 | Real Cost | RD §12.5, §22.2 | `finance/loan_cost.py` → `LoanCostBreakdown` | Tested |
| L6 | Comparison | RD §12.6 | `POST /loans/compare` + S13 table | Tested |
| L7 | Clauses | RD §12.7 | Catalogue `clauses[]` with severity + source; document-extracted clauses | Tested |
| L8 | Loan what-if | RD §12.8 | `finance/what_if.py` (tenure, amount, prepay, missed, rate change) | Tested |
| L9 | Loan doc analyzer | RD §12.9 | S16 + loan extractor + scoped Q&A | Tested |
| L10 | No apply handoff | RD §23.2 | "Apply" absent; explicit note "Applications happen with the lender" | Tested |
| C1–C2 | Cards manage/detail | RD §13.1 | `user_credit_cards` (masked last-4 only) + catalogue link | Tested |
| C3/C6 | Best card for spend | RD §13.2 | `finance/rewards.py` with caps/exclusions/milestones | Tested |
| C4 | Rewards/redemption | RD §13.3 | Per-currency balances; valuation only when catalogue gives a rule; expiry list; category optimisation from spend profile | Tested |
| C5 | New-card exploration | RD §33 | Deferred (optional) | Not started (optional per RD §33) |
| E1/E2 | EMI records | RD §14.1–14.2 | `emis` table; detected from recurring groups with `confirmed=false` | Tested |
| E3 | Calendar | RD §14.3 | Month grid + list, includes card dues and premiums | Tested |
| E4 | WhatsApp reminders | RD §14.3 | `reminders` + scheduler + OpenWA adapter; in-app fallback | Blocked for live WhatsApp send (needs a paired OpenWA session); in-app reminders Tested |
| E5 | EMI what-if | RD §14.4 | `POST /emis/{id}/what-if`; missing rule → `non_computable` + prompt for term | Tested |
| E6 | EMI exploration/comparison, clauses, hidden charges | HW; RD §12.1, §14.4 | EMI what-if "New EMI" tab compares contemplated EMI options (amount/tenure/rate + fees) side-by-side with affordability; existing EMI detail lists its extracted clauses/charges; "Explore refinancing" deep-links to Loans intake prefilled | Tested |
| E7 | No credit-score claims | Owner | Copy review + Saathi rule | Tested |
| I1–I3 | Policies | RD §15.1–15.2 | S40–S42; `user_policies`, `policy_members` | Tested |
| I4/I5 | Explore/compare | RD §15.3–15.4 | `catalogues/insurance.json` (fictional insurers, labelled) + `recommend/insurance.py` | Tested |
| I6 | Consultation | RD §15.5 | `consultation_requests` + Twilio adapter + S46 | Blocked for live call (needs Twilio creds); request lifecycle + signature Tested |
| I7/I8 | Emergency | RD §16 | `POST /insurance/emergency` + S47 | Tested |
| I9/W1 | WhatsApp inbound | RD §17.1 | `/webhooks/openwa` HMAC signature + session scope + inbound routing + opt-out | Blocked for live traffic; signature/inbound/STOP Tested |
| W2 | Twilio webhooks | RD §17.2 | `/webhooks/twilio` signature validation → status update | Blocked for live traffic; signature + status mapping Tested |
| N1 | Notifications | RD §25 | `notifications` table + bell in header | Implemented (in-app bell; processing, reminders, failures) |
| S1–S8 | Security | RD §23 | See §8 | Implemented (see §8; authz, CSRF, consent, masking, deletion tested) |
| Q1 | Response contracts | RD §20.1 | Pydantic schemas enforce | Implemented (currency declared per response — see assumption 17) |
| Q2 | Tests | RD §27 | pytest (finance, parser, dedup, overrides, recommend, extraction fixtures, injection) + vitest + browser checks | Tested (76 backend + 6 frontend tests) |
| Q3 | Demo seed | RD §30 | "Load sample workspace" creating a labelled sample user from fixture files through the real pipeline | Tested |

---

## 5. UI/UX and Design Strategy

Informed by the `ui-ux-pro-max` design-system search (fintech/trust query → *Minimalism & Swiss style*, *IBM Plex Sans*, contrast/focus/reduced-motion rules, "avoid unclear fees", "avoid AI purple/pink gradients"). We **rejected** its generated palette (gold + purple on dark), because the purple accent is the same "AI purple" its own anti-pattern list warns against and doesn't fit the subject. The `frontend-design` skill set the process: build a token plan, check it against generic defaults, then spend boldness in one place.

### 5.1 Design idea: "every number shows where it came from"
VITTRM's value is *trustworthy, source-linked, correctable* data (RD §5). So the one memorable visual device is the **trust mark**: a small, consistent marker attached to every material value. It tells the user whether the value was **Extracted**, **You confirmed**, **Conflicted**, **Missing**, **Sample data** or **Estimate**, and it opens the source. It also carries the RD's product rules into the interface. Everything else stays quiet: a neutral surface, disciplined type and tabular numbers.

Reviewed against generic defaults and revised:
- Rejected: dark-navy "fintech terminal" with a neon accent (a generic default); a cream background with a terracotta accent (a generated-design tell); a SaaS card grid with identical shadows everywhere.
- Chosen: **indigo ink**, in the tradition of Indian indigo and ledger ink, on a cool near-white. **Marigold** is reserved *only* for Vitt Saathi's presence (mic, panel header, speaking state), so the assistant has one recognizable color everywhere (RD §11.1 "one identity").

### 5.2 Tokens
| Token | Hex | Use |
|-------|-----|-----|
| `ink` | `#161D45` | Primary text, headings, sidebar |
| `indigo` | `#3443B5` | Interactive: primary buttons, links, focus ring |
| `marigold` | `#E7A02F` | Vitt Saathi identity only (never body text on white) |
| `paper` | `#F6F7F9` | App background |
| `surface` | `#FFFFFF` | Panels |
| `line` | `#DCDFE7` | Borders/dividers |
| `muted` | `#5B6280` | Secondary text (≥4.5:1 on paper) |
| `positive` | `#17744A` | Inflows, confirmed |
| `caution` | `#94560A` | Conflicted, contingent cost, warnings |
| `critical` | `#B3261E` | Errors, destructive |

Trust-mark styles: Extracted = dotted outline; You confirmed = solid positive with check; Conflicted = caution fill; Missing = dashed muted; Sample data = hatched outline "Sample data"; Estimate = muted "≈ Estimate".

### 5.3 Typography and spacing
- **IBM Plex Sans** (Latin) + **IBM Plex Sans Devanagari** (Hindi), one family with native Devanagari, which serves the English/Hindi/Hinglish requirement (RD §11.2). Bundled via `@fontsource`, so no third-party font requests.
- Tabular lining figures (`font-variant-numeric: tabular-nums`) for all money; Indian digit grouping (₹12,34,567).
- Type scale (1.25 ratio): 12 / 14 / 16 (body) / 20 / 25 / 31 / 39. Line-height 1.5 body, 1.2 headings. Sentence case everywhere; no all-caps labels.
- Spacing: 4-px base; standard density (8/12/16/24/32/48). Radii by hierarchy: 6 px controls, 10 px panels; the sheet uses 16 px top corners only.

### 5.4 Information architecture and navigation (RD §7.1)
```
Desktop (≥1024)                                   Mobile (<1024)
┌────────┬──────────────────────────┬──────────┐  ┌──────────────────────┐
│ VITTRM │  Page header + context   │ Vitt     │  │ header  [bell][me]   │
│ Home   │                          │ Saathi   │  │                      │
│ Loans  │  Module content          │ panel    │  │  content             │
│ Insur. │                          │ (toggle, │  │                      │
│ Cards  │                          │ context  │  │           (Saathi ◉) │
│ EMIs   │                          │ badge)   │  ├──────────────────────┤
│ ────── │                          │          │  │Home Loans Ins Cards EMI│
│ Family │                          │          │  └──────────────────────┘
│ Docs   │                          │          │   Saathi → full-height sheet
└────────┴──────────────────────────┴──────────┘
```
- Primary nav: Home · Loans · Insurance · Cards · EMIs (pillars first, per RD §4). Secondary: Family, Documents & Data, Settings (reminders, consents).
- Mobile: bottom nav with 5 items (≤5 rule); Family/Documents/Settings in the header profile menu; Saathi as a floating marigold button that opens a full-height sheet with context preserved (RD §24.1).
- Deep-linkable routes for every screen (see §6.4). Browser back works throughout.

### 5.5 Screen hierarchy
`/welcome` (S01) → `/onboarding/about` (S02) → `/onboarding/family` (S03) → `/onboarding/statement` (S04) → `/onboarding/processing/:docId` (S05) → `/profile/review` (S06) → `/` (S07).
Loans: `/loans` (S10) → `/loans/need` (S11) → `/loans/results` (S12) → `/loans/compare` (S13) → `/loans/p/:id` (S14, with What-if S15 as a section) → `/loans/analyze` + `/loans/documents/:id` (S16).
Cards: `/cards` (S20) → `/cards/:id` (S21); optimizer S22 embedded in S20 and at `/cards/optimize`.
EMIs: `/emis` (S30 + calendar) → `/emis/:id` (S31 + what-if S32); `/settings/reminders` (S33).
Insurance: `/insurance` (S40) → `/insurance/upload` (S41) → `/insurance/policies/:id` (S42); `/insurance/explore` (S43/S44) → `/insurance/compare` (S45); `/insurance/consult` (S46); `/insurance/emergency` (S47).
`/documents` (S50), `/family` (S51), global Saathi `/saathi` (S08 on mobile; panel on desktop).

### 5.6 Layout strategy
- Left-aligned, single reading column (max ~72ch) for explanations. Data regions use a 12-column grid.
- Dashboard: a "What needs attention" strip first (review items, upcoming dues). Then the four journey entries, as distinct rows with their live summary numbers rather than identical cards. Then money overview (income, spend by category, obligations, surplus), coverage and card snapshots, and quick upload.
- Comparison views: sticky first column (dimension), horizontal scroll *inside* the table only on mobile.

### 5.7 Components (shared, in `frontend/src/components/ui`)
Button, IconButton (with aria-label), Field (label + hint + inline error), Input, Select, Textarea, Checkbox, RadioGroup, Switch, Segmented control (3/6/12 months), FileDrop, Stepper, Tabs, Dialog, Sheet, Toast, Tooltip, Badge, **TrustMark**, **Money**, **SourceLink** (opens SourceDrawer with doc/page/snippet), Stat, DataTable, EmptyState, ErrorState, Skeleton, ProgressSteps, CalendarMonth, CategoryBars (accessible bars, not colour-only), **ToolCard** (calc/comparison/clause results in chat), **SaathiPanel**, **VoiceButton** (idle/connecting/listening/speaking/unavailable).
Radix primitives (via the shadcn-ui MCP component sources) are used for Dialog, Sheet, Tabs, Tooltip and Select, which gives accessible focus management; they are restyled with our tokens.

### 5.8 Responsive behaviour
Breakpoints 375 / 768 / 1024 / 1440. No page-level horizontal scroll. Touch targets ≥44 px. Saathi panel collapses under 1280 px into a toggle, and becomes a sheet under 1024 px.

### 5.9 Accessibility (WCAG 2.1 AA target)
Contrast ≥4.5:1 (tokens chosen for this); visible focus ring (indigo 2 px + offset); keyboard access for all flows; labels are never placeholder-only; errors next to their field plus an error summary on long forms; `aria-live` for processing progress, Saathi responses and voice state; charts show values as text; meaning is never carried by colour alone (trust marks have text); `prefers-reduced-motion` respected; `lang="hi"` on Devanagari spans.

### 5.10 States
Every data view has four states: **loading** (skeletons that reserve layout), **empty** (says what to do next, with a working CTA), **error** (what went wrong and how to fix it, with retry), and **success** (toast that names the action, e.g. "EMI added"). The assistant has a distinct **unavailable** state, e.g. "Vitt Saathi can't reach the AI service. Calculators and your data still work." (RD §26).

### 5.11 Document upload and review
- Upload: drag/drop or pick. The user declares the document type, owner or family member, and, for statements, the account label and 3/6/12-month period. The purpose-based consent line sits beside the upload button. Duplicate checksum → warn before continuing.
- Processing: a staged progress list (Uploaded → Reading → Categorising → Building profile) with live status. Background completion is allowed, and a retry is offered on failure with the specific reason (password-protected, no text layer, unsupported format).
- Review (S06): grouped into Income, Recurring obligations (EMIs/cards/rent/premiums/subscriptions), Categories and merchants, and High-value events. Each item shows a trust mark, source link, and inline correction (category select, "This is my salary", "This is an EMI", "Not recurring"). A "Confirm all shown" button covers the reviewed group only.
- Policy and loan document summaries use the same fact rows, each with a source link and a "Correct" action.

### 5.12 Vitt Saathi interaction pattern
- Header: marigold mark + "Vitt Saathi" + **context badge** (e.g. "Loans", "Insurance · Policy: Care Plus", "Emergency · Mother"). The user can switch to "General".
- Messages: user bubbles on the right; Saathi answers are left-aligned text (not bubbles) with **tool cards** inline (EMI result, cost breakdown, card ranking, clause excerpt) and **Source** chips.
- Voice: one-tap mic. States: connecting → listening (pulsing ring, marigold) → speaking (waveform) → interrupted. Transcripts stream into the same thread. Stop is always visible.
- Mode label when Gemini isn't configured: "Tool mode — answers come from VITTRM calculators and your data; free-form AI is off." Never styled to look like the full AI.

---

## 6. Technical Architecture

### 6.1 Stack (new project — nothing to preserve)
| Layer | Choice | Why |
|-------|--------|-----|
| Backend | **Python 3 + FastAPI + SQLAlchemy 2 + Pydantic v2** | RD §18.1 default; strong typing for contracts |
| DB | **SQLite by default, PostgreSQL via `DATABASE_URL`** | RD names Postgres; exact vendor deferred (RD §33). SQLite = zero setup for hackathon; models stay portable (JSON columns via SQLAlchemy `JSON`) |
| Jobs | FastAPI background tasks + DB-persisted job stage; simple in-process scheduler loop for reminders | Async processing without Redis/Celery complexity |
| PDF | `pypdf` (text + encryption detection) | Pure Python, no system deps |
| Crypto | `cryptography` Fernet for files at rest; `hashlib.scrypt` for passwords | Standard library + one well-known dependency |
| HTTP | `httpx` for OpenWA and Twilio REST | Small server-side adapters; signature validation implemented + tested |
| AI | `google-genai` SDK (lazy-imported; only used when key configured) | RD: Gemini stack |
| Frontend | **React + TypeScript + Vite + Tailwind CSS v4 + React Router + TanStack Query** | Modern, mobile-first; fast dev |
| UI primitives | Radix (Dialog, Tabs, Tooltip, Select…) styled with tokens; `lucide-react` icons | Accessibility for free; SVG icons |
| Tests | pytest (backend), Vitest + Testing Library (frontend), Chrome MCP for UI/responsive checks | RD §27 |

### 6.2 Repository layout
```
paytm-mumbai/
  plan.md  README.md  .gitignore  .env.example
  backend/
    pyproject.toml
    app/
      main.py  config.py  db.py  security.py  deps.py  audit.py
      models.py  schemas.py
      routers/  auth, onboarding, family, documents, profile, loans, cards, emis,
                insurance, ai, consultations, reminders, notifications, webhooks, demo
      services/
        storage.py                 # encrypted object store (local dir)
        statements/ parser.py categorizer.py recurring.py
        profile_engine.py
        extractors/ insurance.py loan.py common.py
        retrieval.py               # document chunks + scoped search
        finance/ emi.py loan_cost.py what_if.py rewards.py affordability.py
        recommend/ loans.py insurance.py
        saathi/ orchestrator.py context.py tools.py router_offline.py gemini.py prompts.py
        channels/ whatsapp.py twilio_voice.py scheduler.py
      catalogues/ loans.json cards.json insurance.json
    fixtures/  (generated sample statement CSV/PDF, sample policy PDF, sample KFS PDF)
    tests/
  frontend/
    src/ app/ (shell, routes)  components/ui  features/<module>  lib/ (api, format)  styles/
```

### 6.3 Data model (RD §19, kept entity-for-entity)
`users`, `consents`*, `sessions`*, `family_members`, `bank_accounts`, `documents`, `document_facts`, `document_chunks`*, `transactions`, `recurring_groups`*, `financial_profiles`, `profile_overrides`, `loan_catalogue`†, `user_loans`, `credit_card_catalogue`†, `user_credit_cards`, `emis`, `insurance_catalogue`†, `user_policies`, `policy_members`, `reminders`, `notifications`*, `conversations`, `messages`, `consultation_requests`, `calculation_runs`*, `audit_events`.
\* = added implementation entities (needed for consent records, sessions, retrieval, recurring grouping, calculation snapshots per RD §23.3, in-app notifications per RD §25).
† = catalogues loaded from versioned JSON files at startup into tables. Each record carries `source`, `last_updated` and `is_mock`.

Fact state on `document_facts` / profile items: `extracted | confirmed | conflicted | missing` (RD §9.4). Transactions carry `category_source: rule|user` and `source_ref` (document id + page/row).

### 6.4 API (RD §20 endpoints kept; additions marked +)
All endpoints are under `/api`, return JSON, and are user-scoped by session. Additions:
`+ /auth/signup|login|logout|me`, `+ /onboarding` (PATCH profile basics), `+ /consents`, `+ /family` CRUD, `+ /policy-members`, `+ /documents/{id}/search` (grounded retrieval), `+ DELETE /documents/{id}`, `+ /profile/review` (items needing review), `+ PATCH /transactions/{id}`, `+ /cards/{id}` PATCH/DELETE, `+ /emis/calendar`, `+ /emis/{id}/confirm`, `+ /insurance/catalogue`, `+ /insurance/policies/{id}`, `+ /consultations/{id}`, `+ /notifications`, `+ /ai/conversations`, `+ /ai/tools/{name}` (tool execution for Live-voice function calls), `+ /ai/status`, `+ /demo/seed` (sample workspace), `+ POST /webhooks/openwa`, `+ /health`.
Common contracts per RD §20.1: `Money{amount,currency}`, `reason_codes[]`, `missing_data[]`, `citations[]`, `catalogue_meta{source,last_updated,is_mock}`, `calculation{inputs,outputs,formula_version}`.

### 6.5 Authentication (deferred provider → simplest robust default)
Email + password (scrypt hash, per-user salt). Server-side session in the `sessions` table; opaque token in an `HttpOnly; SameSite=Lax` cookie (`Secure` when HTTPS). Mutating requests require a same-origin `Origin`/`Referer` check (CSRF). Login attempts are rate-limited per email+IP in memory. The provider is swappable later (RD §33).

### 6.6 Document pipeline (RD Fig. 1: Ingest → Parse → Normalize → Validate → Persist → Serve)
1. **Ingest:** validate type/size (≤15 MB; PDF/CSV). SHA-256 → duplicate check (per user). Encrypt with Fernet → `storage/<uuid>.bin`. Record `documents` row (`processing_status=queued`), audit event.
2. **Parse:** CSV → header-mapped rows. PDF → pypdf per-page text; encrypted → `failed:password_protected`; no text → `failed:no_text_layer` (with Gemini configured: optional page-image extraction, marked low confidence).
3. **Normalize:** statements → transactions (date, amount, direction, description, merchant, category, fingerprint, `source_ref=page/row`). Policies/loan docs → facts with page + snippet.
4. **Validate:** confidence scoring. Totals/balance continuity check for statements. Snippet-must-exist-in-page check for every AI-extracted fact. Conflicts against existing confirmed facts → `conflicted`.
5. **Persist:** transactions deduped by fingerprint; facts; chunks for retrieval; profile rebuilt (overrides applied last).
6. **Serve:** profile slices, facts and chunks to Saathi and tools. Raw file bytes are never sent to the LLM after extraction (RD §4).

### 6.7 Validation & error handling
Pydantic validation on every request. Domain errors use `{error:{code,message,field?}}` with stable codes, such as `DUPLICATE_DOCUMENT`, `PASSWORD_PROTECTED`, `NO_TEXT_LAYER`, `NOT_COMPUTABLE`, `INTEGRATION_NOT_CONFIGURED` and `CONSENT_REQUIRED`. The UI maps codes to plain-language messages with next steps.

### 6.8 Security boundaries
Browser ↔ backend (session cookie). Backend ↔ Gemini/OpenWA/Twilio (server-held secrets only). The browser receives only short-lived Live tokens (RD §35.1). Webhooks are authenticated by signature (OpenWA `X-OpenWA-Signature` HMAC-SHA256 with the webhook secret; Twilio `X-Twilio-Signature` HMAC-SHA1). Every query is scoped by `user_id` (object-level authz).

---

## 7. AI and Integration Plan

> **Verification status:** OpenWA send and webhook contracts are locally tested, but no paired live session has been exercised. Gemini and Twilio still require their configured credentials and live acceptance checks.

| Integration | Status | What we build now | What's needed from the owner |
|-------------|--------|-------------------|------------------------------|
| **Gemini (text, function calling)** — Vitt Saathi chat, optional structured extraction | Requires credentials | `saathi/gemini.py` adapter via `google-genai`; tools declared as function schemas; model id from `GEMINI_MODEL` (**no hard-coded default**). `/api/ai/status` reports `configured/not_configured` | `GEMINI_API_KEY`, `GEMINI_MODEL` (a currently supported model id) |
| **Gemini Live (voice)** | Requires credentials; model id unverified | `POST /api/ai/session-token` mints a short-lived ephemeral token server-side, per RD §35.1's recommendation; browser `VoiceSession` uses `@google/genai` Live connect with mic PCM capture and audio playback; Live function calls go to `POST /api/ai/tools/{name}` so the same deterministic tools run; input/output transcripts are appended to the same conversation | `GEMINI_LIVE_MODEL` (the Live model available at build time — RD §33 notes the owner's "Gemini 3.8 Live" label must not be hard-coded unverified) |
| **OpenWA WhatsApp gateway** | Requires the local `OpenWA/` service, a dedicated paired number and a session-scoped operator key | `channels/openwa.py`: send text through the configured session; HMAC-signed `/webhooks/openwa` receives inbound messages and delivery states; inbound text → linked user → emergency quick-query / Saathi tool mode reply + deep link; "STOP" → opt-out; idempotency on OpenWA's stable event key | `OPENWA_BASE_URL`, `OPENWA_API_KEY`, `OPENWA_SESSION_ID`, `OPENWA_WEBHOOK_SECRET`, public HTTPS URL for webhook |
| **Twilio Programmable Voice** | Requires account, Twilio number, verified destination numbers on trial | `channels/twilio_voice.py`: create call via REST `Calls.json` with inline TwiML (brief consented intro, then `<Dial>` to consultant number), `StatusCallback` → `/api/webhooks/twilio` with signature validation → `consultation_requests.status` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `CONSULTANT_PHONE_NUMBER`, public URL |
| **Catalogues (loans/cards/insurance)** | Local, labelled demo data | Curated JSON with **fictional** lenders/issuers/insurers and illustrative terms; every record shows "Sample data · last updated <date>" | A real data partner later (RD §33) |
| **Statement/policy parsing** | Local | Deterministic parsers + heuristic extractors; Gemini structured extraction when configured | — |

**Behaviour when not configured (labelled, not silent):**
- Chat → **Tool mode.** A deterministic intent router (English + Hinglish keywords) calls the same tools and renders the same cards, with the badge "Tool mode — AI not configured". It never produces free-form financial claims.
- Voice → the mic shows "Voice needs Gemini Live setup", with the setup steps. No fake voice.
- WhatsApp reminder → the reminder row is saved and the in-app notification is created. Delivery status is `not_configured`, and the UI says "WhatsApp isn't connected. You'll see this reminder in VITTRM."
- Consultation → the request is saved with status `not_configured`, and the UI says "Calling isn't set up, so no call was placed. Your request is saved." It never implies a call happened (RD §26).

**Saathi orchestration (RD §11.3, §18.2, App. B):** resolve context → minimal profile slice (A11) → tool allow-list for the context → Gemini function-calling loop (max N steps) → validate tool output + provenance → answer. A **numeric-fidelity guard** checks that every ₹ amount in the narrative appears in some tool output this turn. If one doesn't, the message is flagged and the tool cards stay authoritative. Document text is passed inside clearly delimited "untrusted document content" blocks (RD §23.3).

---

## 8. Data, Privacy, and Security

| Concern | Measure |
|---------|---------|
| Consent (S1) | `consents` rows per purpose: `financial_documents`, `whatsapp_reminders`, `consultation_calls`, and optionally `ai_processing`. Uploads are blocked without `financial_documents` consent (`CONSENT_REQUIRED`); WhatsApp needs opt-in and a verified phone; calls need per-request consent. Consent can be revoked in Settings. |
| Minimization (S2) | Cards: issuer, name and **last 4 digits only**. Input validation rejects 12–19-digit card numbers in any card field. No CVV/PIN/banking passwords are ever requested. Salary optional. |
| At-rest encryption (S3) | Uploaded files are encrypted with Fernet (AES-128-CBC + HMAC) using `VITRAM_DATA_KEY`; a dev key is auto-generated into `backend/.data/` (git-ignored) with a warning. DB-level encryption depends on deployment (Postgres/disk encryption); this is documented, not claimed. |
| In transit | HTTPS in deployment; `Secure` cookie when HTTPS; vendor calls over TLS. |
| Private storage | Files are served only via an authenticated backend route that checks ownership; there is no public bucket or static path. |
| Access control (S4) | Every repository query filters by `user_id`; ids are UUIDs; tests assert cross-user access returns 404. |
| Deletion (S5) | Delete a document (cascades its transactions, facts, chunks and file; rebuilds the profile), delete a family member, delete all my data. |
| Audit (S6) | `audit_events` for upload, document view/download, correction, recommendation, calculation, outbound WhatsApp and call, consent change. Metadata never includes document text or amounts beyond ids. |
| Logging | A structured logger with a redaction filter (card-like numbers, phone numbers, emails). Parsers never log row contents. Request bodies are not logged. |
| AI requests | Minimal profile slice per context, with masked identifiers (policy/account refs masked, e.g. `••••4821`). Family-member data is included only when that member is selected (RD §6.2, §11.4). Document text is delimited as untrusted. |
| Upload safety | Size/type limits; magic-byte check (`%PDF`); CSV size/row caps; symlinks irrelevant (bytes only); filename never used as a path. |
| Secrets | `.env` (git-ignored), `.env.example` without values; frontend never receives server keys; Live uses ephemeral tokens. |
| Regulatory (S8) | Persistent footer note and per-catalogue label: "VITTRM is a decision-support prototype, not a lender, insurer or adviser. Products shown are sample data." Production needs RBI KFS/APR alignment, IRDAI intermediary review and DPDP alignment (RD §23.2). |

---

## 9. Implementation Roadmap

Order follows RD §29 Phases A–H. **One deliberate deviation:** the deterministic finance engine (part of RD Phase D) is built *before* Vitt Saathi core (Phase C), because Saathi's tool-first design requires tools to exist first. Saathi core is then built before the module screens so that each module ships with its panel.

| # | Milestone | Deliverables | Depends on | Acceptance criteria | Tests |
|---|-----------|--------------|------------|---------------------|-------|
| M1 | Foundation | Repo layout, backend skeleton, config, DB models, auth + sessions + consent, audit, encrypted storage, frontend scaffold, tokens, UI kit, app shell + nav + Saathi panel shell | — | Sign up/in/out works; shell navigable on desktop + mobile; no secrets committed | pytest auth/authz; `tsc` + `vite build`; browser check |
| M2 | Profile data layer | Statement upload (CSV + text PDF), processing stages, parser, dedup, categorizer, merchants, recurring, salary/EMI/card/premium detection, cash-flow metrics, profile build, overrides, review screen, onboarding S01–S06, family S03/S51, documents S50 | M1 | Fixture statement → correct txn count/totals; review shows items with trust marks; correction persists and wins on rebuild; duplicate upload warned | parser/dedup/recurring/override unit tests; fixture test |
| M3 | Dashboard | S07 with all RD §8.2 elements + quick upload + data-quality indicator | M2 | All 4 modules reachable; numbers match profile; empty states when no data | component + browser check |
| M4 | Finance engine | EMI, amortization, loan cost breakdown, GST on fees, APR-style annualized cost (IRR), prepayment, missed/late, rate change, affordability, rewards with caps/exclusions/milestones | — | Formula outputs match hand-checked values; missing rules → `not_computable` | full unit suite (RD §27.1) |
| M5 | Vitt Saathi core | Conversations/messages, context packages, tool registry, offline tool mode, Gemini adapter, cards + citations, panel/sheet UI, status | M2, M4 | Tool mode answers loan/EMI/card/insurance questions using tools; badge visible; Gemini path wired and reports not-configured honestly | router + tool tests; context-isolation test |
| M6 | Loans | Catalogue, intake, recommend, results, compare, detail/Real Cost, what-if, loan doc analyzer + scoped Q&A | M4, M5 | RD §31.2 all met | recommend reason-code tests; extraction fixture test; browser run |
| M7 | Insurance | Policy upload/extract/review, summary with sources, explore/recommend/compare, emergency mode, consultation request + Twilio adapter | M2, M5 | RD §31.4 met (Twilio: request lifecycle; real call pending creds) | extraction fixture incl. injection + conflict; emergency filter tests; Twilio signature test |
| M8 | Cards | Add/edit/delete, detail, optimizer, rewards/redemption, better-card-by-category | M4 | RD §31.3 card items | reward tests; browser run |
| M9 | EMIs | Detected + manual EMIs, confirm, calendar (EMIs + card dues + premiums), detail, what-if, reminder settings, scheduler, WhatsApp adapter + webhook | M2, M4 | RD §31.3 EMI items (WhatsApp send pending creds) | what-if tests; webhook verify/signature tests; scheduler test |
| M10 | Voice & channels | Gemini Live session token + browser voice client + tool proxy; WhatsApp inbound routing | M5, M9 | Works when creds provided; unavailable state otherwise | token endpoint test (not configured); manual test w/ creds |
| M11 | Polish & demo | Sample workspace seed (through real pipeline), error states, a11y audit, responsive checks, README setup, demo script per RD §30 | all | RD Appendix A checklist reviewed honestly | e2e journey checks in browser |

---

## 10. Risks and Assumptions

### 10.1 Assumptions (smallest reasonable, recorded per instructions)
1. **Auth** = local email + password; there is no mobile OTP (needs an SMS provider; the provider is deferred in RD §33).
2. **DB** = SQLite default; Postgres supported via `DATABASE_URL` (RD §33 defers the vendor).
3. **Catalogues use fictional institution names** ("Sample data"), so we never attach invented rates or terms to real lenders, issuers or insurers (owner rule + RD §11.4). Terms are illustrative and plausible for India but are **not market data**.
4. **Statement formats:** CSV (flexible header mapping) and text-layer PDF (line heuristics, balance-continuity for debit/credit). Real bank layouts vary; low-confidence rows go to review. Scanned PDFs need Gemini-configured extraction or an unlocked/CSV export.
5. **Categorisation** = deterministic Indian-merchant keyword rules (UPI/NEFT/IMPS/NACH/ACH narration patterns); unknown → "Other". No LLM guessing by default.
6. **Salary** is inferred only from recurring monthly credits with salary-like narration or a stable employer counterparty, and is always shown for confirmation. Multiple candidates → user picks.
7. **Insurance types** in explore: health, term life, traditional life/endowment (HW "others — LIC") and travel (RD §15.3). Parents/family is a health variant (family floater / parents cover).
8. **Annualized cost** = IRR of net disbursal (principal − upfront fees and taxes) vs the EMI schedule, labelled "annualized cost (estimate, APR-style)". It is not presented as a regulatory APR.
9. **GST on fees** = 18%, labelled as an assumption and user-editable, because RD mentions GST without a rate.
10. **Late-payment what-if** uses only the loan's/EMI's stated rule (flat fee and/or % p.a. penal on overdue amount). If absent → `not_computable` with a field to enter it (RD §22.3).
11. **Reminder cadence default** = 3 days before + on due date (RD §14.3 "several days before and on due date"); user-configurable.
12. **Consultation** connects the user to a team-controlled consultant number via Twilio (RD §15.5); no call recording.
13. **Live voice** runs directly browser → Gemini with an ephemeral token (RD §35.1). Tools execute on the backend.
14. **"Apply" handoff** is omitted; loan detail says applications happen with the lender (RD §23.2, S14 "placeholder if permitted").
15. **Card-statement upload (D4) and new-card exploration (C5)** are after core; manual card add ships first (RD §13.1 "where practical", §33).
16. **Dark mode** is not required by the documents; tokens are structured to allow it later.
17. **Currency contract (RD §20.1):** responses declare `"currency": "INR"` (and `"precision": 2` on calculations) once per payload, with every amount rounded to 2 dp, rather than wrapping each number as `{amount, currency}`. Same guarantee, less noise for the UI.
18. **Tool mode language:** when Gemini isn't configured, Vitt Saathi understands English + Hinglish keywords but replies in English templates built only from tool output. Full Hindi/Hinglish replies require Gemini.
19. **Dashboard context tools:** a loan conversation started from the dashboard may use the loan follow-up tools (cost, compare, what-if), because RD §12.1 names "Dashboard/Vitt Saathi → I need a loan for…" as an entry point. Other modules stay isolated.
20. **Salary estimate** uses the median of the latest three salary credits, so a mid-period increment is reflected (the sample shows ₹1,12,450 → ₹1,18,200).
21. **Frequent-merchant spending** (for example Swiggy several times a month) is reported as merchant intelligence, not as a recurring obligation. Recurring detection covers EMIs, rent, premiums, subscriptions, utilities, SIPs, card bills, salary and repeating transfers.
22. **Running headers/footers** (lines repeated on most PDF pages) are stripped before extraction, and **text addressed to AI tools** inside a document is excluded from structured facts and flagged to the user (RD §23.3).
23. **Schema changes** in dev use a small forward-only "add missing nullable columns" sync at startup (no migration tool yet). Production should adopt Alembic migrations.
24. **Voice/Live model ids** come only from configuration. The browser Live client was written against the installed `@google/genai` 2.x type definitions, and the Python token call against `google-genai` 2.25 signatures. Neither was exercised against the live API.

### 10.2 Risks
| Risk | Mitigation |
|------|------------|
| Real bank PDFs fail heuristics | CSV path; review UI; confidence flags; Gemini extraction path when configured |
| No AI credentials → demo lacks free-form AI | Honest Tool mode delivers all calculations/grounded answers; README setup |
| WhatsApp template approval latency | Build + test webhook/signature locally; in-app reminders always work |
| Twilio trial limits (verified numbers only) | Documented; request lifecycle testable without a live call |
| Scope breadth | Loans + Insurance deepest; Cards/EMI narrower but real (RD §32) |
| Git: `~/Desktop` is itself a git repo with unrelated staged deletions | We do **not** commit into it; recommend `git init` inside `paytm-mumbai` (owner decision) |

### 10.3 Conflicts found between sources
- None substantive. HW lists "EMI Statement Intelligence AI" struck through, so it's treated as removed. HW places "Airline, hotel, tickets" under cards; RD §13.3 expresses this as travel/hotel redemption paths, and we follow RD.

### 10.4 Decisions that need owner input (non-blocking; defaults above are in effect)
1. **"AAge Saathi"** (HW): which product this refers to and which qualities (voice-first? tone?) to emulate. We follow RD §11 and copy nothing.
2. Which **Gemini model ids** to use (text + Live) once you have a key.
3. **WhatsApp**: an approved template name/language for reminders, and a public webhook URL.
4. **Twilio**: the consultant destination number and the from number.
5. Whether to `git init` a dedicated repo in `paytm-mumbai/`.

---

## 11. Definition of Done (per feature)
A feature is **Done** only when all hold:
1. **Functional:** the documented behaviour works end-to-end through the real API with persisted data (no hard-coded UI numbers).
2. **Honest data:** every material value shows provenance (trust mark / source link); samples and estimates are labelled; unknowns show "Not available", never 0.
3. **Validation:** server-side validation with field-level errors surfaced inline.
4. **States:** loading, empty, error (with fix/retry) and success states are implemented.
5. **Responsive:** verified at 375 px and ≥1280 px with no horizontal page scroll; touch targets ≥44 px.
6. **Accessible:** keyboard operable, labelled controls, visible focus, contrast AA.
7. **Security:** user-scoped queries, no sensitive logging, consent enforced where required.
8. **Tests:** unit tests for logic (mandatory for finance/parsing/recommendation), plus at least one API test and a browser run for journeys.
9. **Plan updated:** tracker status and any new assumptions recorded here.

---

## 12. Progress Tracker

Legend: ☐ Not started · ◐ In progress · ● Implemented · ✔ Tested · ⛔ Blocked

### Foundation
- ✔ Backend skeleton, config, DB (SQLite default, Postgres via `DATABASE_URL`), full RD §19 data model
- ✔ Auth (scrypt + HttpOnly session cookie), consent records, audit events, CSRF origin check, login rate limit
- ✔ Encrypted document storage (Fernet), private download route with ownership check
- ✔ Frontend scaffold, design tokens, UI kit (trust marks, source drawer, money, fields, sheets), app shell, desktop + mobile navigation

### Profile & documents
- ✔ Onboarding S01–S03 (sign-up, About you with optional salary, Family) — browser-verified
- ✔ Statement upload S04 (3/6/12 months, account label, consent gate) + processing S05 — browser-verified with a real file upload
- ✔ Parser (CSV + text PDF with balance-based direction), dedup (checksum + fingerprint), categoriser, merchant intelligence, recurring + salary/EMI/card/premium detection
- ✔ Profile engine (RD §9.3 structure, fact states, overrides win, conflict detection)
- ✔ Profile review S06 (confirm salary/recurring, recategorise transactions, override income, uncertain directions)
- ✔ Documents & Data S50 (status, extracted facts with correction, re-read, delete with cascade), Family S51
- ✔ Dashboard S07 (Ask/Speak, attention, month in money, journeys, next 30 days, data quality, quick upload)

### Engine & AI
- ✔ Finance engine: EMI, schedule, Real Cost with GST and contingent charges, APR-style estimate, tenure/amount/prepayment/missed/late/rate-change, affordability, rewards with caps/exclusions/valuation rules
- ✔ Vitt Saathi orchestrator, context packages, per-context tool allow-lists, numeric-fidelity guard, citations
- ✔ Tool mode (AI not configured) — labelled in UI; loan/card/EMI/insurance/emergency/document Q&A flows tested
- ⛔ Gemini text adapter — built; offline contract tests with real SDK types pass; **live call not verified** (needs `GEMINI_API_KEY` + `GEMINI_MODEL`)
- ⛔ Gemini Live voice — token endpoint + browser client built; **not verified** (needs key + `GEMINI_LIVE_MODEL`); UI shows honest unavailable state

### Journeys
- ✔ Loans S10–S16 (need intake with collateral/girvi, recommendations with reason codes, comparison, Real Cost, clauses, what-if, KFS analyzer with page-cited terms)
- ✔ Insurance S40–S45, S47 (overview, upload with covered members, summary with sources/corrections, waiting-period status, explore/compare against labelled catalogue, Emergency Mode)
- ⛔ Consultation S46 + Twilio — consented summary preview, request lifecycle, retry, signed webhook tested; **live call needs Twilio creds**
- ✔ Cards S20–S22 (manual add with last-4 only, best-card-for-spend, rewards/redemption, category insights)
- ✔ EMIs S30–S32 (detected/manual/document EMIs, confirm/reject, smart calendar, what-if, new-EMI comparison)
- ⛔ Reminders S33 + WhatsApp — scheduler, cadence settings, opt-in, in-app delivery ✔; **live WhatsApp send needs a paired OpenWA session and scoped API key**

### Quality
- ✔ Backend tests: 76 passing (finance, parsing/dedup/recurring/overrides, extraction incl. injection + conflicts, journeys, Saathi eval, channels/signatures, CSRF, authz, Gemini contract)
- ✔ Frontend: `tsc -b` clean, `vite build` OK (route code-splitting; main chunk 341 KB), `oxlint` 0 errors (fast-refresh warnings only), 6 component/format tests
- ✔ Browser checks (headless Chrome via DevTools protocol — the Chrome MCP extension wasn't connected): welcome, sample workspace, dashboard, review, loans (results/detail/compare/document), cards, EMIs, insurance, policy, emergency, Saathi panel; mobile 390 px dashboard/loans/EMIs/Saathi sheet with no horizontal scroll; full sign-up → upload → processing → review journey
- ◐ Accessibility review — built-in (labels, aria-invalid/describedby, focus rings, text trust marks, reduced motion, 44 px targets); no automated axe/WCAG audit run yet
- ✔ Sample workspace (real pipeline) — ◐ demo script per RD §30 still to write

### Test results (latest run, 2026-09-23)
- `backend: uv run pytest -q` → **76 passed**
- `frontend: npm test` → **6 passed**; `npm run typecheck` → **0 errors**; `npm run build` → **success**

### Session log
- **2026-09-23 / session 1:** Read RD (all sections, both figures) and HW (cropped + transcribed). Checked the environment (Node 22, Python 3.14, uv, SQLite; Postgres installed but not running; no integration credentials). Ran `ui-ux-pro-max` design-system search; used `frontend-design` process. Wrote this plan.
- **2026-09-23 / session 1 (cont.):** Built backend M1–M9 and the full frontend. Fixed issues found in testing: salary split by month names in narrations; frequent merchants mis-detected as obligations; Western digit grouping in backend text (now ₹3,00,000); duplicate salary row; running PDF headers leaking into exclusions; injected AI-directed text shown as a policy condition; KFS EMI appearing before its first due date. Used the shadcn-ui MCP for Radix Sheet/Dialog patterns. Web doc fetches were declined, so vendor API shapes were checked against the installed SDK type definitions instead.

### Milestone M10 — Verify, harden, demo prep (in progress; paused 2026-09-23 for the UI upgrade)
- ✔ **A. Migrations:** Alembic replaces the add-missing-columns workaround. Baseline `0001` + `0002` (`emis.first_due_date`). Pre-Alembic databases are detected and stamped without schema change. SQLite is backed up (online-backup API) before any migration. `python -m app.migrate status|upgrade|backup|restore`. 5 migration tests (fresh = models with zero drift, legacy v1 upgrade preserving data + backup, legacy-current stamp-only, downgrade/upgrade, idempotent). Verified on a disposable **PostgreSQL 14** (zero drift) and the **full suite passes on Postgres**. The developer DB was stamped `0002` in place (non-destructive, data intact: 6 users, 16 documents, 1,040 transactions).
- ✔ **B. Accessibility audit:** `frontend/scripts/a11y-audit.mjs` (axe-core 4.13, WCAG 2.1 A/AA + best practice, 26 routes × desktop/mobile + Saathi sheet = 53 scans, plus keyboard/focus/touch checks). Found and fixed: invalid `dl` structure (policy summary, documents sheet), colour-only inline links (now underlined), unlabelled duplicate nav landmarks, missing `main` on onboarding, empty table headers, weak focus on dashboard ask box, 20 px-tall journey title links, **focus not returned after closing dialogs/sheets and the Saathi panel**. Result: **0 axe violations; 8/8 keyboard/touch checks pass.** Remaining: no screen-reader (VoiceOver/NVDA) session yet; the Radix Select isn't used (native selects), so no custom listbox to test.
- ✔ **Integration fixes from official docs (fetched 2026-09-23):** Gemini ephemeral tokens require API **v1beta** (code used v1alpha — fixed). Official models page lists **`gemini-3.8-live`** (stable, default Live model) and `gemini-3.8-flash` (stable, function calling) — recorded as documented options, still configuration-only and unverified against a key. WhatsApp sends now include `recipient_type`. Twilio webhook signatures now use Twilio's official `RequestValidator` (Twilio's docs advise against hand-rolled validation; the existing test signature still validates).
- ✔ **C. Hindi/Hinglish Tool mode:** language detection (Devanagari / Hinglish markers / English, ambiguous turns inherit the conversation language, then the profile preference), Devanagari digit normalisation, Hindi keywords for intents/amounts (लाख/करोड़)/tenure (साल/महीने)/purposes/relations/collateral, every Tool-mode reply in en/hi/hinglish built from tool output, `lang` on messages, Gemini prompt language hint. 8 tests incl. tool isolation in Hindi. Live Gemini multilingual behaviour **not verified**.
- ☐ **D. Card-statement upload** — paused (not started). Not in RD §28 MVP; RD §13.1 "where practical".
- ☐ **E. New-card exploration** — paused (optional per RD §33).
- ☐ **Phase 3 INTEGRATIONS.md** (per-integration env vars, setup, safe test procedure) — paused; facts gathered above.
- ☐ **Phase 4 DEMO_SCRIPT.md** — paused.

### Milestone M11 — Premium glassmorphism UI upgrade (2026-09-23)
Checklist (visual/UX only — no backend, calculation or workflow changes; no new runtime dependencies):
- ✔ Design tokens (`styles/index.css`): fixed canvas with three soft radial light sources; glass surfaces (`glass-strong` .86 / `glass` .72 / `glass-soft` .56 / `glass-dark`), hairline border + inner highlight, blur 8/16/28 px, navy-tinted layered elevation 1–4, radii scale (chip · control 12 · card 18 · panel 22 · window 28), durations 120/200/320 ms + `ease-out-soft`, indigo focus ring, navy / indigo / saathi gradients, validated chart series colours (`viz-in` #27A876, `viz-out` #8F80F7 on navy — dataviz validator: CVD ΔE 20, normal ΔE 27). `@supports not (backdrop-filter)` → solid surfaces; `forced-colors` → system colours; `prefers-reduced-motion` → no animation/lift.
- ✔ Shared components: `Panel` variants (surface / glass / hero / inset, `interactive` lift), `StatCard`, `SectionHeader`, refined `PageHeader`/`Stat`/`Badge`; buttons (gradient primary, glass secondary, saathi gradient with glow, pressed states); rounded glassy inputs + segmented controls with focus ring; `Modal`/`Sheet` as floating glass windows (inset on desktop, bottom sheet with handle), blurred navy scrim, entrance animation, focus return kept; `EmptyState` with icon tile; glass-dark pill toasts; upload drop zone with visible keyboard focus.
- ✔ App shell: floating navy sidebar (active indicator), floating glass pill top bar (sample badge, Saathi launcher, notifications popover as glass window), floating glass tab bar on phones/tablets with safe-area padding, Saathi FAB. `<main>` is a CSS container so page grids respond to the space left when the Saathi window is open.
- ✔ Home dashboard: navy hero with greeting, **real** 6-month money-in/out grouped bars from `cashflow_metrics.monthly_series` (partial edge months striped and labelled, hover tooltip with net, legend, Chart/Table toggle, screen-reader table always present), four floating stat cards with trust marks, Saathi ask bar inside the hero; attention cards; journey cards; "Due in the next 30 days" timeline with date tiles; "Where the money goes". No statement → three-step onboarding empty state; no numbers shown.
- ✔ Journeys: Loans (navy "Explore" feature card + "Analyse" card, document rows with icon tiles, pill what-if tabs); Insurance (type-icon policy tiles, family coverage avatars); Emergency inherits the new surfaces; Cards (card-face tiles, **masked last 4 only**, read as "ending 4821" by screen readers; tint stable per card id, not rank); EMIs (stat cards, calendar with today marker, weekend tint, readable dates on chips for screen readers, pill scenario tabs).
- ✔ Family (avatars; removing a member now asks for confirmation), Documents & Data, Settings (connected-services status as honest badges — "Tool mode · Gemini not configured" / "Not configured"; danger zone marked; delete-all still requires typing DELETE).
- ✔ Vitt Saathi floating window: desktop glass window beside the page (not covering content), navy header with context chip, Tool-mode notice, glass bubbles, tool cards, typing indicator, visible voice-state chip (connecting / listening / speaking), composer pill; each message carries `lang` (`hi`, `hi-Latn` for Hinglish, `en`); mobile full-height glass sheet. Voice button still says setup is required when Gemini Live isn't configured.
- ✔ Welcome and onboarding: hero light treatment, glass header, progress stepper.
- Verification: see "M11 verification" below.

#### M11 verification (2026-09-23)
- Frontend: `tsc -b` clean · oxlint 0 errors (22 warnings, all pre-existing fast-refresh / ref-in-render notes) · `vitest` 14/14 (6 existing + 8 new in `src/__tests__/m11.test.tsx`: chart table + Indian grouping, partial months, table toggle/net, 6-month window, card face masking, missing last-4, Panel variants, StatCard/EmptyState) · `vite build` OK.
- Backend unchanged: 89/89 pytest.
- Screenshots (1440 / 768 / 390, sample workspace only — fictional data): dashboard, cards, EMIs, loans, insurance, family, documents, settings, Saathi desktop + mobile, welcome.
- Accessibility audit (`frontend/scripts/a11y-audit.mjs`, axe-core 4.13, WCAG 2.1 A/AA + best practice): 53 page scans (26 routes × desktop/mobile + Saathi sheet), **0 violations**; keyboard & touch 8/8 PASS. First M11 run failed "visible focus" on the dashboard ask input (its own outline had been removed) → fixed with a marigold focus ring, re-run passed.

Known gaps / honest notes:
- The Saathi reply in the screenshot is Tool mode; Gemini chat and Live voice remain unverified (no key configured).
- Hinglish user messages get `lang` only when they contain Devanagari; assistant replies always carry the language the backend used.
- Contrast on glass was checked by axe on the rendered pages (solid-enough glass opacities, white text only on the navy hero); not verified in Windows high-contrast mode on a real device.

### Milestone M12 — Reference-driven redesign & product polish (2026-09-23)
Reference screens (`resources/`): `image.png` Home · `image copy.png` Loans · `image copy 2.png` Insurance · `image copy 3.png` Cards · `image copy 4.png` EMIs · `image copy 5.png` Family · `image copy 6.png` Documents & data · `image copy 7.png` Settings. All show empty/new-user states.

Design decisions (from the references, adjusted):
- Lavender-periwinkle canvas with soft light and a faint mountain horizon; glass cards (translucent + blur) with solid fallbacks; deep-indigo floating sidebar with tagline, indigo active pill, setup-progress card and profile card; topbar split into search pill · bell · amber Ask Vitt Saathi · avatar.
- Kept out on purpose: handwritten script captions, motivational quotes, real bank logos on the card illustration, a "financial health score" (VITTRM computes no score — shown instead as a real setup checklist), "Powered by Gemini / Voice enabled" chips (shown only from `/ai/status`), Privacy/Terms/Help footer links (no such pages).
- Illustrations are inline SVG (no image assets, no new dependencies).
- Search is honest: it matches VITTRM pages and the user's own document names, and otherwise sends the question to Vitt Saathi. No fabricated results.

Checklist:
- ✔ Tokens & canvas refresh (lavender scale, sidebar/active/amber/danger washes, layout + control sizes); translucent glass cards (no per-card blur, for scroll performance) with solid/forced-colours fallbacks; `Breadcrumbs`, `PageHero`, `FeatureTile`, `IconTile`, `GlassCard`, `ConfirmDialog`, `PasswordInput`, `Avatar`, inline-SVG illustrations (`components/illustrations.tsx`)
- ✔ App background: `resources/image copy 8.png` → `frontend/src/assets/app-background.jpg` (124 KB JPEG, from 2.4 MB PNG) as one fixed layer (`.app-bg`) on every signed-in and onboarding screen; login and sign-up keep the plain canvas. A soft fade covers a mark in the source image's top-left corner.
- ✔ Shell: collapsible sidebar (icon rail + tooltips, remembered per browser) with tagline, setup-progress card (real steps) and profile card; mobile/tablet drawer; floating topbar with search (⌘K / Ctrl K), notifications, amber Ask Vitt Saathi, avatar dropdown (My profile · Settings · Documents & data · Sign out with confirmation)
- ✔ Home (summary cards, get-started or money panel, real setup checklist, journeys, upcoming, Meet Vitt Saathi with live status chips), Loans (feature chips, Explore/Analyse cards, documents, loan types → prefilled need form, before-you-sign checklist), Insurance (empty hero, features, help + emergency cards), Cards (card-face tiles, empty hero, capabilities, Saathi examples that really ask), EMIs (stat cards, selectable calendar days with details, tip), Family (hero, member cards, dashed add card, relation-prefilled suggestions, sort, confirm-to-remove), Documents & data (upload hub, how-it-works, totals, search / type filter / sort, honest status chips), Settings (icons, explicit Allowed/Not allowed, service notes, danger panel, typed DELETE)
- ✔ Auth: `/login`, `/signup` (split layout, show/hide password, client validation that keeps input, confirm password), session-expired notice (`/login?expired=1` after a 401 while signed in), honest "Forgot password" dialog, `/welcome` kept as an alias of sign-up; unauthenticated users go to `/login` and return to the page they asked for
- ✔ Login / sign-up redesign (2026-09-23, from `image.png`): full-bleed layout at ≥1280 px — a large curved navy panel drawn in SVG (lit rim, orb, glass shards, dot grids; decorative, `aria-hidden`), scaled by page width so its edge stays clear of the right-aligned form; the glass-shapes background (`app-background.jpg`, scaled up and anchored right so its caption sits bottom-right and its marked corner is cropped). 1024–1279 px keeps the rounded navy panel; phones stack. Note: this puts the background image on login/sign-up, which the earlier request had excluded, because the new mock shows it.
- ✔ Profile `/profile`: personal information (PATCH `/onboarding/about`), mobile number replace/remove, Saathi reply language, notifications & contact status, security (password change via **new** `POST /auth/password` — current password required, other sessions ended, rate-limited, audited; explained as unavailable for sample workspaces), financial-profile summary with trust marks and user-entered salary
- ✔ Saathi: wider/narrower toggle on desktop, close; pages without their own context (Documents, Settings, Profile) now set the general context instead of keeping the previous page's. Add/edit card and EMI forms moved to wide sheets
- ✔ Verification (2026-09-23): `tsc -b` clean · oxlint 0 errors (21 pre-existing warnings) · vitest 21/21 (7 new in `src/__tests__/m12.test.tsx`) · pytest 92/92 (3 new in `tests/test_auth_password.py`) · `vite build` OK · screenshots 1440 / 768 / 390, fresh account (empty states) and sample workspace · accessibility audit (`scripts/a11y-audit.mjs`, now also covering `/profile`, `/login`, `/signup`): 61 scans, **0 violations**, keyboard & touch 8/8 PASS. The first M12 run found four issues (duplicate "Account" landmark on Profile, brand text outside landmarks on login/sign-up, search input without its own focus ring, an inline link under 24 px) — all fixed and re-verified.

Known gaps / honest notes:
- Search finds VITTRM pages and the user's own document names only; everything else is sent to Vitt Saathi as a question.
- Theme choice is not offered (the app has one light theme). Email change, password reset, verification, OTP and social login are not built.
- The background image carries the text "YOUR MONEY · A BRIGHTER YOU" at its right edge, which can sit behind page content on wide screens.
- One test account (`m12-empty-…@example.com`) was created in the local dev database for empty-state screenshots.

Backend gaps (not built, shown honestly in the UI): password reset by email, email/phone verification, OTP, social login.

### Milestone M13 — Computer vision & document intelligence (2026-09-23)
Audit (before changes): text PDFs + CSV only; scanned PDFs rejected with NO_TEXT_LAYER; no image or receipt support; no OCR engine installed (no tesseract/onnx/numpy). Available: pypdf, Pillow, google-genai 2.25 (supports `Part.from_bytes` + `response_json_schema` on `generate_content`), Swift 6.3 + Apple Vision on this Mac. Gemini not configured.

Decisions:
- OCR providers behind one interface (`app/services/vision/`): **macOS Vision** (on-device, via a small Swift helper built on first use — nothing leaves the machine), **Gemini** (explicit opt-in `OCR_PROVIDER=gemini`, model id from env only; documented example `gemini-3.8-flash`), **none** (clear "not configured" error). `auto` = on-device if available, else none — never silently sends documents to a cloud model.
- Images are validated by magic bytes, orientation-corrected, downscaled, and re-encoded (drops EXIF/GPS) before OCR. Lines are rebuilt from word boxes (layout) so tables and receipts keep their columns.
- OCR-derived facts get lower confidence and the document is marked as read from a scan; nothing is auto-confirmed.
- Receipts reuse Document + DocumentFact (provenance, review state); linking to a transaction is a user choice; no transactions are created.

Checklist (priority order):
- ✔ P1 Vision layer (`app/services/vision/`: providers, image safety, layout rows) + Swift helper; scanned PDFs and photos for policies, loan documents, statements and receipts. **Verified end to end on this Mac** with real OCR (test `test_real_on_device_ocr_reads_a_photo_of_a_receipt`, and a browser run: photo → 11 values → correct transaction suggested).
- ✔ P1 Upload with real progress (XHR), "Take a photo" (rear camera), image preview, "Reading the scan" step; accepted types follow what the server can read (`/ai/status` → `vision`).
- ✔ P1 Extracted-data review (`ExtractedReview`): confirm / correct / reject per value with source line, page link, confidence and "Read from scan" marks; `POST /documents/{id}/facts/{fid}/reject`.
- ✔ P1 Receipt scanner (`/documents/receipts/new`, `/documents/receipts/:id`): merchant, date, invoice no., GSTIN, subtotal, CGST/SGST/IGST/cess, total, items, payment method; subtotal+tax check; transaction suggestions (amount ±₹1, −2…+5 days, merchant words) with reasons; user-chosen link; no transaction created.
- ✔ P1 Vitt Saathi `document` context (`document_summary` + scoped `documents_search`), "Ask" per document, chat attachments (paperclip → upload → summary), summary card; EN/HI/Hinglish replies.
- ✔ P2 Spending insights (`/insights`): full-month category trends (±20% and ₹1,000), possible subscriptions (confirm/dismiss), unusual payments in the last 90 days (merchant spike, category spike, large first payee, possible duplicate; "I expected this"), neutral wording, explain-this-transaction (also from Review).
- ✔ P2 Cash-flow estimate (`/forecast`, Home card): confirmed income or entered salary, confirmed recurring debits, confirmed EMIs, entered card dues, expected payments; entered or statement balance; per-item exclusions; assumptions and missing data listed; pressure callout.
- ✔ P2 Card user-entered benefits (`user_benefits`, shown as "You entered", card-number guard).
- ✔ P3 Goals (`/goals`, nav): target, date, contributions (± withdrawals), monthly needed, average surplus shown as an estimate beside it.
- ✔ P3 Reminders per item (mute/unmute, cancel one) — muted items are never re-scheduled.
- ✔ P3 Password reset with an SMTP boundary (single-use hashed tokens, 30 min, no account enumeration, all sessions end); `/forgot-password`, `/reset-password`. Not configured here → honest message.
- ✔ Migration `0003` (goals, goal_contributions, expected_payments, password_resets; user_credit_cards.user_benefits; reminder_preferences.muted). The local dev DB was auto-upgraded at start-up with a backup (`backend/.data/backups/vitram-20260923-122128-pre-0003.db`); all changes are additive.
- ✔ Verification (2026-09-23): pytest **121/121** (29 new: `test_vision.py` 17 incl. one real on-device OCR test, `test_intelligence.py` 12) · vitest **25/25** · `tsc -b` clean · oxlint 0 errors (21 warnings, same set as before M13) · `vite build` OK · accessibility audit 75 page scans (new: insights, forecast, goals, receipt scan, a receipt review page produced by real OCR, forgot/reset password) — one heading-order issue on the empty Goals page, fixed and re-checked (0 violations); keyboard & touch 8/8 PASS · browser run of the full receipt flow against the running app.

Follow-up fixes (2026-09-23, from user report):
- **Repeated 409s on upload** — the duplicate-file error was returned but never shown: `FileDrop` hid errors once a file was chosen, so each click re-sent the upload. Errors now show in both states; the 409 carries the existing document's id/type (`error.details`), and every upload flow (policy, loan, receipt, statement, Saathi attachment) shows "You've already uploaded this file" with **Open it** and **Read it again** (reprocess with the current pipeline, incl. OCR). Test `test_duplicate_upload_says_which_document`.
- **Vision hard to find** — added a "Scan documents with your camera" section on Home (live OCR status), a scan button in the top bar on every page (only when OCR is available), a "Photos and scans are read on this device" label and a prominent "Take a photo" button in upload boxes, and a "Read from a photo" badge on analysed loan documents.
- **Receipt page 404s** (`GET /documents/{id}/receipt`) — "Read it again" on a duplicate that had been uploaded as a *different* type (e.g. a statement dropped on the receipt page) opened the receipt page for a non-receipt. Now the notice says what type it was uploaded as and only offers **Open it**; the receipt page shows "Receipt not found" instead of retrying a 404.
- **Live camera scanner (OpenCV.js)** — "Scan with camera" in every photo-capable upload box opens a full-screen scanner: live `getUserMedia` video, real-time document detection on a 640-px copy of each frame (grey → blur → Canny with thresholds from mean brightness → morphological close → contours → largest convex 4-corner polygon ≥ 18% of the frame), a smoothed outline with a stability ring, and auto-capture after ~1 s steady (Auto can be switched off; the shutter always works). Then drag or arrow-key the four corners, perspective-correct (`warpPerspective`), and pick a look: **Enhanced** (background-division shadow removal + contrast), **Colour**, or **Black & white** (adaptive threshold); rotate; **Use this scan** hands a JPEG to the normal upload → on-device OCR. Frames never leave the browser. Library: `@techstark/opencv-js` 4.12 (Apache-2.0), a 10.9 MB asset loaded only when the scanner opens. Falls back to the phone camera app / file upload when there's no camera, permission is denied, or the page isn't a secure context.
  - Bug found while testing: the Emscripten module is a thenable whose `then()` returns itself, so resolving a Promise with it looped forever and froze the page. The loader now waits on `then()` and strips it (regression test added).
  - Verified (2026-09-23) in headless Chrome with a fake camera feed (a receipt photographed at an angle on a desk): detection → auto-capture → corner adjust (keyboard) → Enhanced/B&W preview → Use this scan → OCR → ₹808.81 / 9 Mar 2026 / GST ₹38.51 / UPI read, and the matching BigBasket transaction suggested. axe: 0 violations in the live, adjust and preview phases at 390 px and 1440 px; no horizontal scroll. **Not tested on a physical phone camera** in this session.
  - vitest 27/27 · `tsc -b` clean · oxlint 0 errors, no new warnings · `vite build` OK.

Existing features reused rather than rebuilt: loan analyser & real-cost engine, policy extraction/summary/"Ask about this policy", Emergency help, card optimiser (caps, exclusions, redemption), EMI calendar/what-ifs/new-EMI comparison, family members, consents, WhatsApp/Twilio integration code.

Not built / not verified (honest):
- Gemini chat, Gemini Live voice and Gemini vision: adapters built and contract-tested; no key configured, so **not verified live**.
- WhatsApp and Twilio: unchanged, still not configured; no live message or call. SMTP: no live email sent.
- OCR outside macOS needs `OCR_PROVIDER=gemini` (cloud) — no local engine was installed on purpose.
- HEIC photos are refused with advice to use JPG. Multi-page photo sets are separate uploads.
- Family: data stays per member as before; explicit cross-member permissions (e.g. sharing a member's data with another login) aren't built — VITTRM has one login per workspace.
- Card statement upload (D4, paused in M10) still not built.

### Next milestone (M10/M11)
1. Owner supplies Gemini key + model ids → verify chat function-calling and Live voice end to end; then enable Gemini-assisted extraction for scanned PDFs.
2. Owner pairs the OpenWA WhatsApp session and supplies its scoped key plus Twilio credentials and a public HTTPS URL → verify live reminder send, delivery-status webhooks, inbound emergency query and a consultation call.
3. Accessibility audit (automated + keyboard pass), RD §30 demo script, card-statement upload (D4), Alembic migrations, Postgres run.
