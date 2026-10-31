"""Runtime configuration.

Every external integration is optional. When its settings are missing the
feature reports `not_configured` instead of pretending to work.
Model identifiers are deliberately left without defaults (RD §33): the owner
must set the Gemini model ids that are available at build time.
"""

from functools import lru_cache
from pathlib import Path

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
    # Apply pending Alembic migrations at start-up (SQLite files are backed up first).
    auto_migrate: bool = True
    max_upload_mb: int = 15

    # Gemini (Vitt Saathi chat + optional structured extraction)
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    # Bound provider waits so chat can fall back to Tool mode instead of
    # leaving the user on an endless spinner. Gemini rejects deadlines <10s.
    gemini_timeout_ms: int = 10_000
    # Gemini Live (in-app real-time voice)
    gemini_live_model: str | None = None

    # OCR / document vision. auto = on-device Apple Vision when available (macOS), otherwise none.
    # Gemini vision is used only when set explicitly (documents are then sent to Google).
    ocr_provider: str = "auto"  # auto | macos | gemini | none
    # Model id for Gemini vision; falls back to GEMINI_MODEL. Never defaulted in code.
    gemini_vision_model: str | None = None
    ocr_max_pages: int = 30

    # Outgoing email (password reset). Not configured → reset links can't be sent, and the UI says so.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True

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

    # Assumption A9 in plan.md: GST rate on loan service fees, user-editable per calculation.
    default_gst_on_fees_pct: float = 18.0
    # Catalogue freshness threshold (RD §26 "stale product catalogue").
    catalogue_stale_days: int = 90

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

    @property
    def openwa_configured(self) -> bool:
        return bool(self.openwa_base_url and self.openwa_api_key and self.openwa_session_id)

    @property
    def openwa_webhook_configured(self) -> bool:
        return bool(self.openwa_session_id and self.openwa_webhook_secret and len(self.openwa_webhook_secret) >= 16)

    @property
    def whatsapp_configured(self) -> bool:
        """Channel-level name retained for API/UI compatibility."""
        return self.openwa_configured

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
