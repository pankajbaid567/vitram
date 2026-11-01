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
#
# Envelope encryption. Every stored file gets its own random data key (DEK); the file is encrypted with the DEK, and the DEK is encrypted
# ("wrapped") with the master key. Blob layout:  b"VTR2" | wrapped-DEK length (2 bytes) | wrapped DEK | Fernet(DEK)(file).
# Rotating the master key therefore re-wraps a ~100-byte header per file instead of re-encrypting every file, and a leaked DEK exposes one file.
# Objects written before this scheme are plain Fernet tokens under the master key and are still read (and upgraded by app.rotate_keys).
#
# Master keys: VITRAM_DATA_KEY is the primary (used to encrypt); VITRAM_DATA_KEY_PREVIOUS lists retired keys that may still decrypt.

from cryptography.fernet import MultiFernet  # noqa: E402

ENVELOPE_MAGIC = b"VTR2"

_masters: list[bytes] | None = None


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


def master_keys() -> list[bytes]:
    """Primary key first, then retired keys (decrypt-only)."""
    global _masters
    previous = [k.strip().encode() for k in (get_settings().vitram_data_key_previous or "").split(",") if k.strip()]
    keys = [_load_key(), *previous]
    if _masters != keys:
        _masters = keys
        _reset_caches()
    return keys


_fernet: Fernet | None = None
_multi: MultiFernet | None = None


def _reset_caches() -> None:
    global _fernet, _multi
    _fernet = _multi = None


def fernet() -> Fernet:
    """The primary master key."""
    global _fernet
    master_keys()
    if _fernet is None:
        _fernet = Fernet(master_keys()[0])
    return _fernet


def multi() -> MultiFernet:
    """Encrypts with the primary, decrypts with any master key."""
    global _multi
    keys = master_keys()
    if _multi is None:
        _multi = MultiFernet([Fernet(k) for k in keys])
    return _multi


def encrypt_bytes(data: bytes) -> bytes:
    dek = Fernet.generate_key()
    wrapped = fernet().encrypt(dek)
    return ENVELOPE_MAGIC + len(wrapped).to_bytes(2, "big") + wrapped + Fernet(dek).encrypt(data)


def _split(blob: bytes) -> tuple[bytes, bytes] | None:
    if not blob.startswith(ENVELOPE_MAGIC):
        return None
    n = int.from_bytes(blob[4:6], "big")
    return blob[6:6 + n], blob[6 + n:]


def decrypt_bytes(data: bytes) -> bytes:
    try:
        parts = _split(data)
        if parts is None:                                   # legacy: a Fernet token under the master key
            return multi().decrypt(data)
        wrapped, body = parts
        return Fernet(multi().decrypt(wrapped)).decrypt(body)
    except InvalidToken as exc:  # wrong or retired-and-removed key, or the file was tampered with
        raise ValueError("Stored file could not be decrypted") from exc


def rewrap(blob: bytes) -> bytes | None:
    """The blob protected by the *primary* master key, or None when it already is.

    Envelope blobs only get their wrapped DEK replaced (the encrypted body is byte-for-byte unchanged); legacy blobs are re-encrypted whole.
    """
    parts = _split(blob)
    if parts is None:
        return encrypt_bytes(decrypt_bytes(blob))
    wrapped, body = parts
    try:
        fernet().decrypt(wrapped)
        return None
    except InvalidToken:
        pass
    try:
        new_wrapped = multi().rotate(wrapped)
    except InvalidToken as exc:
        raise ValueError("Stored file could not be decrypted") from exc
    return ENVELOPE_MAGIC + len(new_wrapped).to_bytes(2, "big") + new_wrapped + body


def encrypt_str(value: str) -> str:
    """Short values (a phone number) are encrypted directly under the master key; ``rotate_str`` moves them to a new one."""
    return fernet().encrypt(value.encode()).decode()


def decrypt_str(value: str) -> str:
    try:
        return multi().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored value could not be decrypted") from exc


def rotate_str(value: str) -> str:
    return multi().rotate(value.encode()).decode()


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


def phone_lookup_hash(e164: str, key: bytes | None = None) -> str:
    """Keyed hash of a phone number, for matching inbound messages without decrypting. Stored under the primary key."""
    return hmac.new(key or master_keys()[0], e164.encode(), hashlib.sha256).hexdigest()


def phone_lookup_candidates(e164: str) -> list[str]:
    """The hash under every master key, so a lookup still works while rows are being re-keyed after a rotation."""
    return [phone_lookup_hash(e164, k) for k in master_keys()]


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
