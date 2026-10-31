"""Password hashing, session tokens, at-rest encryption, masking and log redaction."""

import base64
import hashlib
import hmac
import logging
import re
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

log = logging.getLogger("vitram.security")

# --- passwords (scrypt, stdlib) -------------------------------------------

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, digest_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return hmac.compare_digest(digest, expected)


# --- session tokens -------------------------------------------------------


def new_session_token() -> tuple[str, str]:
    """Returns (token for cookie, sha256 id stored in DB)."""
    token = secrets.token_urlsafe(32)
    return token, token_id(token)


def token_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- at-rest encryption ---------------------------------------------------

_fernet: Fernet | None = None


def _load_key() -> bytes:
    settings = get_settings()
    if settings.vitram_data_key:
        return settings.vitram_data_key.encode()
    key_file = settings.data_dir / "dev.key"
    if key_file.exists():
        return key_file.read_bytes().strip()
    if settings.env == "production":
        raise RuntimeError("VITRAM_DATA_KEY must be set in production")
    key = Fernet.generate_key()
    key_file.write_bytes(key)
    key_file.chmod(0o600)
    log.warning("Generated a development encryption key at %s. Set VITRAM_DATA_KEY for real deployments.", key_file)
    return key


def fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_key())
    return _fernet


def encrypt_bytes(data: bytes) -> bytes:
    return fernet().encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    try:
        return fernet().decrypt(data)
    except InvalidToken as exc:  # key rotated or file tampered
        raise ValueError("Stored file could not be decrypted") from exc


def encrypt_str(value: str) -> str:
    return encrypt_bytes(value.encode()).decode()


def decrypt_str(value: str) -> str:
    return decrypt_bytes(value.encode()).decode()


# --- masking --------------------------------------------------------------


def mask_tail(value: str | None, keep: int = 4) -> str | None:
    if not value:
        return None
    clean = re.sub(r"\s", "", value)
    if len(clean) <= keep:
        return "••" + clean
    return "••••" + clean[-keep:]


def normalize_indian_phone(raw: str) -> str | None:
    """Returns E.164 (+91XXXXXXXXXX) for an Indian mobile number, else None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        return None
    return "+91" + digits


def phone_lookup_hash(e164: str) -> str:
    return hmac.new(_load_key(), e164.encode(), hashlib.sha256).hexdigest()


def mask_phone(e164: str) -> str:
    return e164[:3] + " ••••• " + e164[-4:]


# Card-number-like digit runs (12–19 digits, optionally spaced/dashed)
CARD_LIKE = re.compile(r"\b(?:\d[ -]?){12,19}\b")


def looks_like_full_card_number(value: str) -> bool:
    return bool(CARD_LIKE.search(value or ""))


# --- log redaction --------------------------------------------------------

_REDACTIONS = [
    (CARD_LIKE, "[redacted-number]"),
    (re.compile(r"\+?91[ -]?[6-9]\d{9}\b|\b[6-9]\d{9}\b"), "[redacted-phone]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[redacted-email]"),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        record.msg = redact(msg)
        record.args = ()
        return True
