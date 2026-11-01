"""WhatsApp gateway port.

The rest of the backend (reminder dispatch, inbound webhooks) depends on the
:class:`WhatsAppGateway` protocol, never on a vendor module. Two adapters implement it:

* :mod:`~app.services.channels.meta_cloud`: Meta's **official** WhatsApp Cloud API (production; the
  specification's locked decision). Business-initiated reminders use an approved template.
* :mod:`~app.services.channels.openwa`: a self-hosted *unofficial* gateway for development and demos.

``WHATSAPP_PROVIDER`` picks one; callers never know which.
"""

from typing import Protocol, TypedDict

from app.config import get_settings


class NotConfigured(Exception):
    """The gateway has no credentials/URL, so nothing can be sent."""


class SendError(Exception):
    """A send failed. ``retryable`` tells the scheduler whether to try again."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class InboundMessage(TypedDict):
    id: str | None
    sender: str  # digits only, country code included; "" when the sender can't be resolved
    text: str
    is_group: bool


class StatusUpdate(TypedDict):
    message_id: str | None
    status: str | None  # sent | delivered | read | failed
    error: str | None


class WhatsAppGateway(Protocol):
    name: str
    signature_header: str            # request header carrying the webhook signature (lower-case)
    idempotency_header: str | None   # request header carrying a provider event id, when the provider has one

    def configured(self) -> bool: ...

    def webhook_configured(self) -> bool: ...

    def send_text(self, to_e164: str, body: str) -> str:
        """Free-form message (a reply). Returns the provider's message id."""

    def send_reminder(self, to_e164: str, text: str, params: list[str]) -> str:
        """Business-initiated reminder. ``text`` is the rendered message; ``params`` are its
        template variables (item, amount, date) for providers that require an approved template."""

    def verify_signature(self, raw_body: bytes, header: str | None) -> bool: ...

    def verify_subscription(self, query: dict) -> str | None:
        """One-time webhook handshake (``GET``). Returns the challenge to echo, or None to refuse."""

    def session_matches(self, payload: dict) -> bool:
        """True when a (validly signed) webhook belongs to *this* deployment's number/session."""

    def parse_webhook(self, payload: dict) -> tuple[list[InboundMessage], list[StatusUpdate]]: ...


def whatsapp() -> WhatsAppGateway:
    """Return the adapter selected by ``WHATSAPP_PROVIDER``."""
    provider = (get_settings().whatsapp_provider or "openwa").lower()
    if provider == "meta":
        from app.services.channels.meta_cloud import MetaCloudGateway

        return MetaCloudGateway()
    if provider == "openwa":
        from app.services.channels import openwa

        return openwa.OpenWAGateway()
    raise NotConfigured(f"Unknown WHATSAPP_PROVIDER {provider!r}; use 'meta' or 'openwa'.")


def resilient_send(name: str, fn):
    """Send through the gateway's circuit breaker. Only transient failures (network, 5xx, 429) count against the gateway; a rejected
    destination or a malformed request does not. While the circuit is open the send fails fast as a *retryable* SendError, so the reminder
    scheduler backs off instead of every queued reminder waiting on a dead gateway."""
    from app import resilience

    try:
        return resilience.call(name, fn, is_dependency_failure=lambda exc: isinstance(exc, SendError) and exc.retryable)
    except resilience.CircuitOpen as exc:
        raise SendError(str(exc), retryable=True) from exc
