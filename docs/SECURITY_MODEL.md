# Security model

What VITRAM protects, from whom, with which controls, and what is deliberately *not* covered. Each control names the code that implements it and the
test that proves it; if a claim here has no test, it says so. Reporting a vulnerability: see [`SECURITY.md`](../SECURITY.md).

## Assets and trust boundaries

| Asset | Where it lives | Sensitivity |
|---|---|---|
| Bank statements, policies, loan documents | encrypted objects in R2 (or local disk) | high: financial PII |
| Extracted facts, transactions, profile | PostgreSQL | high |
| Phone number | PostgreSQL, encrypted; keyed hash for lookup | medium: PII |
| Passwords, sessions | PostgreSQL (hashed / token hashes) | high |
| Master encryption key | environment of the API only | critical |

```
browser ── TLS ──► Cloudflare Worker ──► Render API ──► Neon PostgreSQL
                    (edge limiter,            │  └────► Cloudflare R2 (ciphertext only)
                     security headers)        └────► Upstash Redis (counters, cache; no documents)
WhatsApp gateway ──signed webhook──► Worker ──► API
```

Trust boundaries: the browser is untrusted; every other component is operated by the project owner but is **not** trusted with plaintext documents (R2
holds ciphertext, Redis never sees document content, logs are redacted).

## Threats (STRIDE)

| Threat | Example | Control | Proof |
|---|---|---|---|
| **S**poofing | stolen or guessed password | Argon2/bcrypt-class hashing, per-email and per-IP sign-in limits, session tokens stored as hashes, `HttpOnly` + `SameSite=Lax` cookie | `test_auth_password.py`, `test_ratelimit.py`, `test_security.py` |
| Spoofing | forged WhatsApp webhook | HMAC signature over the raw bytes, per-provider; wrong-session events dropped | `test_whatsapp_providers.py` |
| **T**ampering | cross-site request changes data | Origin check on every cookie-authenticated state change | `test_security.py` |
| Tampering | edited stored file | authenticated encryption (Fernet): a modified blob fails to decrypt | `test_key_rotation.py::test_a_wrong_key_or_a_tampered_file_is_refused` |
| Tampering | two writers overwrite each other | optimistic concurrency (`If-Match` 412, database version check 409) | `test_concurrency.py` |
| Tampering | double submit / replay of a write | `Idempotency-Key` | `test_idempotency.py` |
| **R**epudiation | "I never deleted that" | append-only audit events with request ids; account erasure anonymises them rather than deleting | `test_privacy.py` |
| **I**nformation disclosure | user A reads user B's data | (1) every query filters by owner, proven for every route by a generated access matrix; (2) Row Level Security in PostgreSQL as a second lock; (3) cache keys include the user id | `test_access_matrix.py`, `test_rls.py`, `test_cache.py` |
| Information disclosure | bucket or database leak | files encrypted before upload with per-file keys (envelope); phone encrypted; documents never in logs | `test_storage_backends.py`, `test_key_rotation.py` |
| Information disclosure | secrets or PII in logs/metrics/traces | redacting log filter; metric labels are route templates; trace SQL carries statements, never parameters | `test_security.py`, `test_observability_metrics.py` |
| Information disclosure | XSS exfiltrates data | strict Content-Security-Policy (below), React escaping, JSON responses carry `default-src 'none'` | headers verified in the live browser run |
| **D**enial of service | flood of requests | edge limiter (per IP), per-user token buckets, in-flight and queue-depth load shedding, bulkheads, upload size and type checks | `test_throttle.py`, `test_resilience.py` |
| Denial of service | a dead dependency stalls every request | circuit breakers, timeouts, fail-open limiter | `test_resilience.py` |
| **E**levation of privilege | forged object id in a URL | 404 (not 403) on someone else's id, for every route | `test_access_matrix.py` |
| Elevation | malicious document text steering the assistant | document text is data; model output is verified against deterministic tool results; amounts that do not match are replaced | `test_saathi.py`, `test_documents.py` |
| Elevation | vulnerable dependency | `pip-audit` and `npm audit` in CI | CI `audit` job |

## Data isolation, in three layers

1. **Application.** Every query is scoped by owner. `test_access_matrix.py` reads the route list from the app itself, so a new endpoint is covered the day it is
   added: it must reject anonymous callers (401) and answer 404 to another user's ids, or be listed as public with a reason.
2. **Database (Row Level Security).** `app/rls.py` and migration `0016` give every table with an owner column a policy: a session that has declared its user
   (`app.user_id`, set per transaction, safe behind a pooling proxy) sees and writes only that user's rows, even for a query written *without* a `WHERE`.
   Sessions that declare nobody (sign-in, webhooks, workers) are unrestricted, so enabling it cannot break system paths.
   **Verified by running the entire backend suite (607 tests) as a PostgreSQL role without `BYPASSRLS` with `RLS_ENABLED=true`**; that run found one real
   problem (erasing an account anonymises audit rows, which a declared user may not do), now handled by an explicit `rls.system()` context.
   *Caveat:* Neon's default owner role has `BYPASSRLS` (checked), so on Neon the policies only apply once the API connects as a separate role. Create one with
   [`deploy/sql/create_app_role.sql`](../deploy/sql/create_app_role.sql), use its URL as `DATABASE_URL`, keep the owner URL for migrations, and set `RLS_ENABLED=true`.
   Tables owned only through a parent (`policy_members`, `goal_contributions`) have no owner column and rely on layer 1.
3. **Cache.** Cached pages are keyed by user id and data version, so one user can never be served another's page.

## Encryption and key management

* **Envelope encryption.** Each stored file gets its own random data key; the file is encrypted with it (Fernet: AES-128-CBC + HMAC-SHA256), and the data key is
  wrapped with the master key and stored in the blob header (`VTR2`). A leaked data key exposes one file.
* **Master keys.** `VITRAM_DATA_KEY` encrypts; `VITRAM_DATA_KEY_PREVIOUS` (comma-separated) lists retired keys that may still decrypt. Phone numbers are encrypted
  under the master key directly, and their lookup hash is an HMAC under it (so lookups try every key while a rotation is in flight).
* **Rotation procedure** (zero downtime, safe to repeat):
  1. generate a new key (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`);
  2. set `VITRAM_DATA_KEY=<new>` and `VITRAM_DATA_KEY_PREVIOUS=<old>`; deploy (everything still reads, new writes use the new key);
  3. run `python -m app.rotate_keys --dry-run`, then `python -m app.rotate_keys`: it re-wraps each file's ~100-byte header (the encrypted body is untouched),
     upgrades pre-envelope files, and re-encrypts phone numbers;
  4. when it reports `unreadable: 0`, remove the old key from `VITRAM_DATA_KEY_PREVIOUS`.
  Proven by `test_key_rotation.py` (including a three-key chain, legacy blobs, S3 pagination, and phone lookups mid-rotation).
* **Backups** exclude the key by design; keep it in a secret manager separately. `scripts/verify_backup.sh` proves a backup restores.

## Content-Security-Policy

Served by the Worker for the app (`frontend/public/_headers`):

```
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:;
media-src 'self' blob:; connect-src 'self' https://generativelanguage.googleapis.com wss://generativelanguage.googleapis.com;
worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'
```

No inline or third-party scripts. `'unsafe-inline'` is allowed for **styles only** (React sets `style` attributes); removing it needs nonces or hashes on the
build output. The Gemini origins are for the optional in-browser voice mode. It was rolled out as `Content-Security-Policy-Report-Only` first and promoted
after the live browser journeys ran with zero violations. JSON responses from the API carry `default-src 'none'`, `nosniff`, `X-Frame-Options: DENY`, `no-store`.

## Sessions and abuse

Sign-in and recovery have their own sliding-window limits (`app/ratelimit.py`); everything else is covered by the token buckets in `app/throttle.py`
(read 240/min, write 60/min, upload 8/min, assistant 15/min plus a daily cap). Deleting an account needs the password, erases files first, and cascades
through every table (tested table by table).

## Not covered / known gaps

* No MFA, no device list or remote sign-out, no session rotation on password change. (Plan: `docs/FUTURE.md`.)
* The unofficial WhatsApp gateway (OpenWA/Baileys) violates WhatsApp's terms and can get a number restricted; it is for demos. Production should use Meta's Cloud API.
* Anonymous rate limiting keys on the client IP the platform reports; behind Cloudflare that can be an edge address, which is why the Worker also limits per real client IP.
* `'unsafe-inline'` for styles (above). Row Level Security does not apply to a `BYPASSRLS` role (above).
* Fernet uses AES-128; moving to AES-256-GCM would need a new blob version (`VTR3`), which the envelope header makes straightforward.
* The sample data is fictional, and "priced" products are labelled as samples; there is no real lender, insurer or payment integration to attack.
