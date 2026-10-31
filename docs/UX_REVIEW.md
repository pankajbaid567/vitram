# UX review and improvement plan

Reviewed in a real Chrome against the sample workspace (fictional data), at 1440px and 390px, with scripted crawls
(Chrome DevTools Protocol) plus manual reading of the screenshots.

## Recruiter rating: 86 / 100

| Area | Score | Why |
|---|---|---|
| Product thinking | 18/20 | A real problem (what do my loans, cards and policies actually cost me?), clear provenance on every figure (Extracted / Estimate / You confirmed), consent-first design, emergency mode for insurance. |
| Engineering depth | 22/25 | FastAPI + SQLAlchemy + Alembic, deterministic finance engine with versioned snapshots, provider-neutral WhatsApp port with two adapters, worker + scheduler, rate limiting, encrypted uploads. |
| Quality and testing | 18/20 | 518 backend tests (88% coverage), 48 frontend tests, generated access matrix, browser journey and accessibility checks in CI. |
| UI / UX polish | 15/20 | Consistent design system, mobile bottom nav, honest empty and error states. Held back by the issues below. |
| Docs and operability | 13/15 | Architecture, ADRs, deploy, go-live, doctor command, health and readiness endpoints. |

Held back by: heavy decorative backgrounds competing with content, a first screen that asks for sign-up before
showing value, brand naming drift (VITTRM in the UI, VITRAM in the repo), and a few small-tap-target clusters on phones.

## Button and link audit (verified in the browser)

- 37 screens visited; 455 buttons and 832 links seen; every distinct internal link target (78) loads a real page.
- 0 links with an empty or `#` target, 0 external links, 0 "page doesn't exist" results.
- Eight buttons looked inert to the crawler. Checked by hand, all are real:
  - **Account menu (SU)**, **Dashboard "Table"**, the three **loan tabs**, **"View clause"** and **"Not an EMI"** all respond
    to real input. The crawler had clicked synthetically and watched for DOM changes that were not there.
  - **Dashboard "Ask"** with an empty box deliberately opens the assistant. On `/saathi` it is already open, so nothing changes.
- Genuine defect found and fixed: **Forecast → Add expected payment** posted an empty form and showed a raw server
  message ("String should have at least 1 character"). It now validates first and says what is missing.
- Settings → *Allow* on WhatsApp reminders correctly returns "Add your mobile number first" when no number is saved.
  It works as designed; see P1-3 for making it actionable.

## Improvement plan

### P0 (done in this pass)
1. Forecast form validation with field-level messages.

### P1 (next)
1. **Show value before sign-up.** Put "Open sample workspace" next to the headline on /welcome, not under the form.
2. **Quieter background.** The faint "YOUR MONEY / A BRIGHTER YOU" watermark crosses content on wide screens; it is baked into `frontend/src/assets/app-background.jpg`, so the fix is a clean export of that image without the text.
3. **Make permission errors actionable.** "Add your mobile number first" should link to the profile field.
4. **Truncated stat captions** on the dashboard cards; allow two lines instead of clipping.
5. **Tap targets.** 20 controls under 32px on the emergency screen at 390px (relationship chips, small links); raise to 40px.

### P2
1. One brand name across UI, repo and docs (decision for the owner: VITTRM or VITRAM).
2. Dashboard: lead with the single most urgent item (next EMI) and collapse the rest below.
3. First-run checklist ("Set up VITTRM · 3 of 4") should be dismissible once complete and link to each step.
4. Add skeleton states for the two slowest screens (loan results, insights).
5. Table/chart toggle on the dashboard: remember the choice per user.

### P3
1. Hindi UI labels for the main navigation (the assistant already speaks Hindi and Hinglish).
2. Illustrations for empty states in Family, Goals and Documents.
3. Keyboard shortcut sheet (the ⌘K search exists but is undocumented).

## How to repeat this review

`make e2e`, `make journey` and `make a11y` cover the flows; the crawler used for this review lives outside the repo.
