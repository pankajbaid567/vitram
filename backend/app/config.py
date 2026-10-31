"""Runtime configuration.

Every external integration is optional. When its settings are missing the
feature reports `not_configured` instead of pretending to work.
Model identifiers are deliberately left without defaults (RD §33): the owner
must set the Gemini model ids that are available at build time.
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    database_url: str = f"sqlite:///{BACKEND_DIR / '.data' / 'vitram.db'}"
    data_dir: Path = BACKEND_DIR / ".data"
    # Fernet key for encrypting uploaded files at rest. Auto-generated in dev.
    vitram_data_key: str | None = None
    # Public origin of the web app, used for CSRF origin checks and deep links.
    app_origin: str = "http://localhost:5173"
    # Public HTTPS base URL of this API, needed for OpenWA/Twilio webhooks.
    public_api_url: str | None = None
    session_days: int = 7
    log_format: str = "text"            # text | json
    rate_limit_backend: str = "memory"  # memory (per process) | database (shared across workers)
    # Run the reminder loop inside the API process. Set false when a dedicated `python -m app.worker` runs it.
    run_scheduler: bool = True
    # Force the session cookie's Secure flag on/off. Unset: on in production, otherwise follows the
    # request scheme (behind a TLS-terminating proxy run uvicorn with --proxy-headers so that is correct).
    session_cookie_secure: bool | None = None
    # Apply pending Alembic migrations at start-up (SQLite files are backed up first).
    auto_migrate: bool = True
    max_upload_mb: int = 15

    # Gemini (Vitt Saathi chat + optional structured extraction)
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    # Bound provider waits so chat can fall back to Tool mode instead of
    # leaving the user on an endless spinner. Gemini rejects deadlines <10s.
    gemini_timeout_ms: int = 10_000
    # Let the model *propose* policy/loan fields from document text. Off by default: it sends document text to Google.
    # Each proposal is verified against a verbatim quotation on its page (services/ai_extraction.py) and needs the user's consent.
    ai_extraction: bool = False
    ai_extraction_max_chars: int = 60_000
    # Gemini Live (in-app real-time voice)
    gemini_live_model: str | None = None

    # OCR / document vision. auto = on-device Apple Vision when available (macOS), otherwise none.
    # Gemini vision is used only when set explicitly (documents are then sent to Google).
    ocr_provider: str = "auto"  # auto | macos | gemini | none
    # Model id for Gemini vision; falls back to GEMINI_MODEL. Never defaulted in code.
    gemini_vision_model: str | None = None
    ocr_max_pages: int = 30
    # Upper bound for one on-device OCR run (a freshly compiled helper can be slow on its first launch).
    ocr_timeout_seconds: int = 180

    # Outgoing email (password reset). Not configured → reset links can't be sent, and the UI says so.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True

    # Which WhatsApp gateway adapter to use: "openwa" (unofficial, development/demo) or "meta" (official Cloud API).
    whatsapp_provider: str = "openwa"

    # Meta WhatsApp Cloud API (the specification's production channel). Names match the usual Meta env vars.
    whatsapp_token: str | None = None            # system-user access token (bearer)
    whatsapp_phone_number_id: str | None = None  # the sending number's id (not the number itself)
    whatsapp_app_secret: str | None = None       # signs inbound webhooks (X-Hub-Signature-256)
    whatsapp_verify_token: str | None = None     # shared secret for the one-time webhook subscription handshake
    whatsapp_graph_version: str = "v21.0"
    # Business-initiated messages must use an approved template with three body variables: {{1}} item, {{2}} amount, {{3}} date.
    whatsapp_reminder_template: str | None = None
    whatsapp_template_language: str = "en"
    whatsapp_timeout_seconds: float = 15.0

    # Self-hosted OpenWA WhatsApp gateway
    openwa_base_url: str | None = None
    openwa_api_key: str | None = None
    openwa_session_id: str | None = None
    openwa_webhook_secret: str | None = None
    openwa_timeout_seconds: float = 15.0

    # Twilio Programmable Voice (insurance consultation calls)
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_verify_service_sid: str | None = None
    twilio_from_number: str | None = None
    consultant_phone_number: str | None = None

    # Legacy setting accepted for installations already using SMTP_USER.
    smtp_user: str | None = None

    # Assumption A9 in docs/spec/plan.md: GST rate on loan service fees, user-editable per calculation.
    default_gst_on_fees_pct: float = 18.0
    # Catalogue freshness threshold (RD §26 "stale product catalogue").
    catalogue_stale_days: int = 90

    @field_validator("rate_limit_backend", mode="before")
    @classmethod
    def _normalise_backend(cls, v):
        v = (v or "memory").strip().lower() if isinstance(v, str) or v is None else v
        if v not in ("memory", "database"):
            raise ValueError("RATE_LIMIT_BACKEND must be 'memory' or 'database'")
        return v

    @field_validator("whatsapp_provider", mode="before")
    @classmethod
    def _normalise_provider(cls, v):
        """Blank means the default; anything unknown fails at start-up rather than at the first send."""
        v = (v or "openwa").strip().lower() if isinstance(v, str) or v is None else v
        if v not in ("openwa", "meta"):
            raise ValueError("WHATSAPP_PROVIDER must be 'openwa' or 'meta'")
        return v

    def production_problems(self) -> list[str]:
        """Misconfigurations that must stop a production start (empty list = fine)."""
        if self.env != "production":
            return []
        problems = []
        if not self.vitram_data_key:
            problems.append("VITRAM_DATA_KEY is required: uploaded files are encrypted with it, and a generated development key would be lost on redeploy.")
        host = urlparse(self.app_origin).hostname or ""
        if not self.app_origin.startswith("https://") and host not in ("localhost", "127.0.0.1"):
            problems.append(f"APP_ORIGIN must be an https:// URL (got {self.app_origin!r}); it gates cross-site requests and builds deep links.")
        if self.session_cookie_secure is False and host not in ("localhost", "127.0.0.1"):
            problems.append("SESSION_COOKIE_SECURE=false is only acceptable on localhost.")
        return problems

    def production_warnings(self) -> list[str]:
        """Things that work but deserve a second look (reported by `python -m app.doctor`)."""
        warnings = []
        if self.env == "production" and self.whatsapp_provider == "openwa":
            warnings.append("WHATSAPP_PROVIDER=openwa is an unofficial gateway with a ban risk; use 'meta' for a real launch.")
        if self.env == "production" and self.is_sqlite:
            warnings.append("SQLite is the development database; use PostgreSQL in production.")
        if self.env == "production" and self.auto_migrate:
            warnings.append("AUTO_MIGRATE=true applies migrations at start-up; prefer a backed-up `alembic upgrade head` release step.")
        return warnings

    def assert_production_ready(self) -> None:
        problems = self.production_problems()
        if problems:
            raise RuntimeError("Refusing to start in production:\n  - " + "\n  - ".join(problems))

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_model)

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def gemini_live_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_live_model)

    def cookie_secure(self, request_scheme: str) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.env == "production" or request_scheme == "https"

    @property
    def openwa_configured(self) -> bool:
        return bool(self.openwa_base_url and self.openwa_api_key and self.openwa_session_id)

    @property
    def openwa_webhook_configured(self) -> bool:
        return bool(self.openwa_session_id and self.openwa_webhook_secret and len(self.openwa_webhook_secret) >= 16)

    @property
    def meta_configured(self) -> bool:
        return bool(self.whatsapp_token and self.whatsapp_phone_number_id and self.whatsapp_reminder_template)

    @property
    def meta_webhook_configured(self) -> bool:
        return bool(self.whatsapp_phone_number_id and self.whatsapp_app_secret and self.whatsapp_verify_token)

    @property
    def whatsapp_configured(self) -> bool:
        """Can the *selected* WhatsApp provider send? (channel-level name kept for API/UI compatibility)."""
        return self.meta_configured if self.whatsapp_provider == "meta" else self.openwa_configured

    @property
    def twilio_configured(self) -> bool:
        return bool(
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_from_number
            and self.consultant_phone_number
        )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
