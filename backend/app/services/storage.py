"""Private, encrypted object storage (RD §23.1).

Files are Fernet-encrypted on write and only readable through authenticated
backend routes. The storage key is a random id — user filenames never touch
the filesystem.
"""

import secrets

from app.config import get_settings
from app.security import decrypt_bytes, encrypt_bytes


def _dir():
    d = get_settings().data_dir / "objects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def put(data: bytes) -> str:
    key = secrets.token_hex(16)
    (_dir() / f"{key}.bin").write_bytes(encrypt_bytes(data))
    return key


def get(key: str) -> bytes:
    if not key.isalnum():
        raise ValueError("Invalid storage key")
    return decrypt_bytes((_dir() / f"{key}.bin").read_bytes())


def delete(key: str) -> None:
    if not key.isalnum():
        return
    path = _dir() / f"{key}.bin"
    if path.exists():
        path.unlink()
