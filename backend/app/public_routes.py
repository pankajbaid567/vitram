"""The only API operations reachable without a session, each with the reason it is safe.

This list is deliberately small and explicit. A test walks the whole route table and fails if any route not
named here answers an anonymous caller, so adding a public endpoint means adding it (and a justification) here.
"""

PUBLIC: dict[tuple[str, str], str] = {
    ("GET", "/api/health"): "liveness probe",
    ("GET", "/api/ready"): "readiness probe (no secrets in the body)",
    ("POST", "/api/auth/signup"): "creates an account",
    ("POST", "/api/auth/login"): "signs in (rate limited, non-enumerating)",
    ("POST", "/api/auth/logout"): "idempotent; clears the caller's own cookie",
    ("POST", "/api/auth/password-reset/request"): "non-enumerating by design",
    ("POST", "/api/auth/password-reset/confirm"): "authorised by a single-use token",
    ("GET", "/api/auth/password-reset/status"): "reports whether e-mail is configured",
    ("POST", "/api/auth/email-verification/confirm"): "authorised by a single-use token",
    ("POST", "/api/demo/workspace"): "creates a labelled sample account",
    ("GET", "/api/demo/fixtures"): "lists generated sample files",
    ("GET", "/api/demo/fixtures/{name}"): "downloads a generated sample file",
    ("GET", "/api/webhooks/whatsapp"): "provider handshake, authorised by a verify token",
    ("POST", "/api/webhooks/whatsapp"): "authorised by the provider's signature over the raw body",
    ("POST", "/api/webhooks/twilio"): "authorised by Twilio's signature",
}
