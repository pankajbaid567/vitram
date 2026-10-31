# Security

VITRAM handles financial documents, so security issues matter. This is a prototype, but it is built to be
reviewed: the design is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#security-model) and every claim below is covered by a test.

## Reporting a vulnerability

Please **don't open a public issue** for a security problem. Use GitHub's *Report a vulnerability* (Security tab →
Advisories) on this repository, or email the maintainer listed on the GitHub profile. Include what you found, how to
reproduce it and what you think the impact is. You will get an acknowledgement within a few days.

## What is in scope

The application code in this repository: authentication and sessions, per-user data isolation, upload handling,
webhook verification, encryption at rest, consent enforcement, and the container/CI configuration.
Out of scope: the third-party services it integrates with (Meta, Twilio, Google, OpenWA), and the fictional sample catalogues.

## Controls (and where they are tested)

| Control | Test |
|---|---|
| Passwords hashed with scrypt; session tokens stored only as a SHA-256; `HttpOnly`, `SameSite=Lax`, `Secure` in production | `test_security.py`, `test_journeys.py` |
| CSRF: state changes must come from the app's origin; foreign origins and cookie-without-origin are rejected | `test_journeys.py` |
| Every route is authenticated unless it is on the explicit allow-list in `app/public_routes.py` | `test_access_matrix.py` |
| One user can never read, change or delete another user's object (404, nothing echoed) | `test_access_matrix.py` |
| Webhooks verify the provider's HMAC over the raw bytes, de-duplicate replays, ignore other sessions | `test_whatsapp_providers.py`, `test_meta_gateway.py`, `test_consultations.py` |
| Uploaded files are encrypted at rest; type, size and magic bytes are checked; EXIF is stripped from images | `test_documents.py`, `test_vision.py` |
| Outbound WhatsApp re-checks consent and a verified phone at send time; `STOP` is honoured immediately | `test_channels.py`, `test_whatsapp_providers.py` |
| Login and recovery endpoints are rate limited (optionally shared across workers) | `test_ratelimit.py` |
| Logs never contain phone numbers, e-mail addresses, card numbers, tokens or document text | `test_operability.py`, `test_doctor.py` |
| Unexpected errors return a request id, never internals | `test_operability.py` |
| Production refuses to start without an encryption key and an `https` origin | `test_operability.py` |
| Dependencies are scanned for known vulnerabilities in CI (`pip-audit`, `npm audit`) | CI `audit` job |
| Users can export everything held about them and delete their account | `test_privacy.py` |

## Known limits

- The in-memory rate limiter is per process unless `RATE_LIMIT_BACKEND=database`.
- WhatsApp via OpenWA is an *unofficial* gateway with a ban risk: development only. Use the Meta Cloud API in production.
- The encryption key (`VITRAM_DATA_KEY`) is read from the environment. There is no key rotation tooling yet, and losing the key makes uploaded files unreadable.
- No CSP is set on HTML pages (the OpenCV.js scanner needs `wasm-unsafe-eval`); the API sets a strict CSP on JSON.
- This is decision-support software over *sample* data: it is not a regulated lender, insurer, broker or adviser.
