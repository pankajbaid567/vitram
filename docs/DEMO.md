# Demo script (≈ 2 minutes for the core, 8 for everything)

Use a fresh, labelled **sample workspace**. These are fictional institutions, terms and people; VITRAM is a decision-support prototype, not a lender, insurer or broker. Start every demo by showing whether Gemini, OpenWA and Twilio are actually connected. Never claim an external message, call or live offer unless its provider status proves it.

**Two-minute core:** steps 1, 3 (loans), 4 (cards) and 6 (emergency mode). Everything runs from *Open sample workspace*, with no keys.

1. Sign in and open the common dashboard. Show the setup checklist, four journeys, money-in/out, upcoming dues, and trust/source marks.
2. Open Documents & Data. Upload the sample bank statement through the real pipeline, show processing, then review salary, category, recurring EMI and any uncertain values. Correct one item and show the dashboard/profile change. Mention that raw documents are not repeatedly sent to Vitt Saathi.
3. Ask Vitt Saathi for a loan purpose and amount. Show reason-coded recommendations, compare at least two, open Real Cost and separate scheduled cost from contingent late charges. Change tenure or prepayment and show the deterministic what-if. Upload the sample KFS and open a page-cited term.
4. Open Cards. Add or use at least two masked cards; ask which to use for a purchase. Show caps, exclusions, reward currency, caveats and why the top option fits. Never display a full card number.
5. Open EMIs. Confirm a detected obligation, switch between month and week calendar, test missed-payment and prepayment scenarios, and point out the explicit unknown-charge state. Show in-app reminder delivery. Only demonstrate WhatsApp send to an opted-in, verified controlled number if the configured OpenWA session is ready.
6. Open Insurance. Upload/review a sample policy, inspect coverage, exclusions, waiting periods and claim documents with source pages. Compare labelled sample plans. Select a family member and event in Emergency Mode; show person-scoped policy shortlist and non-guaranteed claim guidance.
7. Open Consultation. Preview exactly what context will be shared and where the call goes. Only place a consented call to a verified controlled destination if the Voice configuration is complete. Otherwise show the honest not-configured state.
8. Test resilience: disconnect Gemini and show Tool mode; withdraw WhatsApp consent and show queued sends become in-app; show no fabricated rates, fees, claim approval or credit score.

Acceptance evidence to capture: an API/test result for each calculation and extraction fixture, screenshots at phone and desktop widths, source-page and correction examples, signed webhook/idempotency results, screen-reader pass, and real provider IDs/status only for controlled live tests. See [`STATUS.md`](STATUS.md) for the remaining gates.
