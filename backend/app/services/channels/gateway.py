"""WhatsApp gateway port.

The rest of the backend (reminder dispatch, inbound webhooks) depends on the
:class:`WhatsAppGateway` protocol, never on a vendor module. Today the only
adapter is :mod:`app.services.channels.openwa`, a self-hosted *unofficial*
gateway suited to development and demos. An adapter for Meta's official WhatsApp
Cloud API would implement the same protocol and be returned by :func:`whatsapp`
without touching the scheduler or the webhook router.
"""

from typing import Protocol, TypedDict


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

    def configured(self) -> bool: ...

    def webhook_configured(self) -> bool: ...

    def send_text(self, to_e164: str, body: str) -> str:
        """Send a plain-text message; return the provider's message id."""

    def verify_signature(self, raw_body: bytes, header: str | None) -> bool: ...

    def session_matches(self, payload: dict) -> bool:
        """True when a (validly signed) webhook belongs to *this* deployment's session."""

    def parse_webhook(self, payload: dict) -> tuple[list[InboundMessage], list[StatusUpdate]]: ...


def whatsapp() -> WhatsAppGateway:
    """Return the configured WhatsApp gateway adapter."""
    from app.services.channels import openwa

    return openwa.OpenWAGateway()
