# Go-live: plugging in your keys and phone

Everything that can be built and tested without your credentials has been. This is the order to turn the live integrations on.
After each step, run `python -m app.doctor` (read-only; it never sends anything and never prints a secret): the named line should
turn green. Record what you observe in [`STATUS.md`](STATUS.md), moving items from *Not verified* to *Verified*.

```bash
cd backend && cp ../.env.example ../.env       # then edit ../.env
uv run python -m app.doctor --offline          # config only: no network
uv run python -m app.doctor                    # + read-only provider probes
```

Do the steps in order; each is independent of the ones after it. Use **controlled recipients you own** and, for WhatsApp, an opted-in test number.

## 0. Baseline (2 min)

`doctor` should show: `database ✓`, `configuration ✓`, `encryption key ✓` (set `VITRAM_DATA_KEY`; see `docs/DEPLOY.md`), everything else "not configured".
Start the app (`make api` + `make web`, or `docker compose up`) and open the sample workspace once.

## 1. Gemini: chat, languages, extraction (≈10 min)

Set `GEMINI_API_KEY`, `GEMINI_MODEL` (and `GEMINI_LIVE_MODEL` for voice). `doctor`: **`Gemini ✓ model … is available`**.
In the sample workspace, open Vitt Saathi on **Cards** and ask:

| Ask | Expect |
|---|---|
| "Which card should I use for a ₹8,000 flight?" (also in Hindi and Hinglish) | A *tool card* (card ranking) and an answer whose ₹ figures match it (Voyager ≈ 800 miles, ₹400); `mode: gemini` |
| Something off-topic | Declined politely |
| A question whose answer isn't in your data | "I don't know" / not found, not an invented figure |

Then unplug the key (or set a wrong one) and confirm the chat falls back to *Tool mode* with a notice. **AI extraction** (optional): set
`AI_EXTRACTION=true`, grant the *AI processing* consent in Settings, upload the sample policy; facts marked "AI-assisted reading" must each show a quoted snippet.
**Voice**: open voice in the panel, allow the microphone, speak, interrupt it, check the transcript.

## 2. Twilio Verify: phone possession (≈5 min)

Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`. `doctor`: **`Twilio account ✓`, `Twilio Verify ✓`**.
In *Profile*: add *your* number → *Send code* → enter the SMS code → it shows **Verified**. (WhatsApp stays off until this passes.)

## 3. WhatsApp: pick one provider

### 3a. Meta Cloud API (production path)
Follow [`INTEGRATIONS.md`](INTEGRATIONS.md#production-meta-whatsapp-cloud-api-whatsapp_providermeta): business verification, number, token, **approved Utility template** with three variables, then set the `WHATSAPP_*` variables and `PUBLIC_API_URL` (HTTPS). In Meta's console set the callback `{PUBLIC_API_URL}/api/webhooks/whatsapp` + verify token and subscribe to **messages**.
`doctor`: **`WhatsApp (Meta Cloud API) ✓ number … quality GREEN`** (then confirm the template shows *Approved* in Meta; the doctor can't see that).

### 3b. OpenWA (development only; dedicated spare number)
Pair the number in OpenWA, create the session key, set `WHATSAPP_PROVIDER=openwa` and the `OPENWA_*` variables, register the webhook `{PUBLIC_API_URL}/api/webhooks/whatsapp`.
`doctor`: **`WhatsApp (OpenWA) ✓ session ready; webhook registered`**.

### The controlled test (both)
1. *Settings → Reminders*: tick consent, enable WhatsApp. (The page says why if it isn't active.)
2. On an EMI, **Send now**. **Expect:** the message arrives; the response says "Sent on WhatsApp"; status becomes *Delivered*, then *Read*.
3. Reply from your phone: *"Mother is in hospital, which policy applies?"* **Expect:** an answer naming the policy, with a link back to the app (sample workspace data).
4. Reply **STOP**. **Expect:** a confirmation; the settings page shows WhatsApp off; **Send now** again goes in-app only and *says so*.
5. Outage: stop the gateway (or set a wrong token), **Send now**. **Expect:** "will retry"; the in-app notification still appears; a later retry succeeds when restored.
6. (Optional) Re-deliver the same webhook (Meta/OpenWA dashboards can replay): **no second reply**.

## 4. SMTP: verification and reset e-mail (≈3 min)

Set `SMTP_HOST`, `SMTP_FROM`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `APP_ORIGIN`. `doctor`: **`SMTP e-mail ✓ … accepted the connection and login (nothing sent)`**.
Sign up, request verification and a password reset: both mails arrive, links work once, and an unknown address gets the same neutral response.

## 5. Twilio Voice: consultation call (≈5 min)

Set `TWILIO_FROM_NUMBER`, `CONSULTANT_PHONE_NUMBER` (a number you control) and `PUBLIC_API_URL`. `doctor`: **`Twilio Voice ✓`**.
*Insurance → Consultation*: read the preview, consent, request. **Expect:** your verified phone rings, bridges to the consultant number, statuses update to *Completed*; an unverified number is refused.

## 6. Final pass

`python -m app.doctor` has no ✗ and no unexplained !. Run `make e2e` and `make a11y` against the deployed URL. Update `docs/STATUS.md`. If you deploy to a host, follow [`DEPLOY.md`](DEPLOY.md) and set `ENV=production`.

## Kill switches

| To stop… | Do |
|---|---|
| all outbound reminders | `RUN_SCHEDULER=false` and stop the worker |
| WhatsApp only | clear `WHATSAPP_REMINDER_TEMPLATE` (or the gateway URL): reminders fall back to in-app |
| the AI | unset `GEMINI_API_KEY`: the assistant runs in Tool mode |
| model reading of documents | `AI_EXTRACTION=false` |
| one user's WhatsApp | they reply `STOP`, or revoke consent in Settings |
