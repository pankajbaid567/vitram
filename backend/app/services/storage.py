"""Private, encrypted object storage (RD §23.1).

Files are Fernet-encrypted on write and only readable through authenticated backend routes. The storage key
is a random id: user filenames never touch the filesystem or the bucket.

Two interchangeable backends behind the same three functions (``put``/``get``/``delete``):

* ``local``: files under ``DATA_DIR/objects``; needs a persistent disk.
* ``s3``: any S3-compatible bucket (Cloudflare R2 has a free tier), for hosts with no disk. The bytes stored
  there are already ciphertext, so the bucket never holds anything readable.
"""

import secrets
from functools import lru_cache
from typing import Protocol

from app.config import get_settings
from app.security import decrypt_bytes, encrypt_bytes


class _Backend(Protocol):
    def put(self, key: str, blob: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def keys(self): ...   # iterate stored object keys (key rotation)


class _LocalBackend:
    def _path(self, key: str):
        d = get_settings().data_dir / "objects"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{key}.bin"

    def put(self, key: str, blob: bytes) -> None:
        self._path(key).write_bytes(blob)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def keys(self):
        d = get_settings().data_dir / "objects"
        return (p.stem for p in sorted(d.glob("*.bin"))) if d.exists() else iter(())


class _S3Backend:
    def __init__(self, client, bucket: str):
        self._client, self._bucket = client, bucket

    @staticmethod
    def from_settings() -> "_S3Backend":
        s = get_settings()
        missing = [n for n in ("s3_endpoint_url", "s3_bucket", "s3_access_key_id", "s3_secret_access_key") if not getattr(s, n)]
        if missing:
            raise RuntimeError(f"STORAGE_BACKEND=s3 needs {', '.join(m.upper() for m in missing)}")
        import boto3   # optional extra: `uv sync --extra s3`
        from botocore.config import Config
        client = boto3.client("s3", endpoint_url=s.s3_endpoint_url, aws_access_key_id=s.s3_access_key_id,
                              aws_secret_access_key=s.s3_secret_access_key, region_name=s.s3_region,
                              config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}))
        return _S3Backend(client, s.s3_bucket)

    def put(self, key: str, blob: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=f"objects/{key}.bin", Body=blob)

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=f"objects/{key}.bin")["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=f"objects/{key}.bin")   # idempotent on S3

    def keys(self):
        for page in self._client.get_paginator("list_objects_v2").paginate(Bucket=self._bucket, Prefix="objects/"):
            for obj in page.get("Contents", []):
                name = obj["Key"].removeprefix("objects/")
                if name.endswith(".bin"):
                    yield name[:-4]


@lru_cache
def _backend() -> _Backend:
    kind = get_settings().storage_backend
    if kind == "s3":
        return _S3Backend.from_settings()
    if kind == "local":
        return _LocalBackend()
    raise RuntimeError(f"Unknown STORAGE_BACKEND {kind!r}: use 'local' or 's3'")


def put(data: bytes) -> str:
    key = secrets.token_hex(16)
    _backend().put(key, encrypt_bytes(data))
    return key


def get(key: str) -> bytes:
    if not key.isalnum():
        raise ValueError("Invalid storage key")
    return decrypt_bytes(_backend().get(key))


def delete(key: str) -> None:
    if not key.isalnum():
        return
    _backend().delete(key)


def rotate_all(dry_run: bool = False) -> dict:
    """Re-protect every stored object with the primary master key. Idempotent; an unreadable object is reported, not fatal."""
    from app.security import rewrap

    done = skipped = failed = 0
    for key in _backend().keys():
        try:
            new = rewrap(_backend().get(key))
        except ValueError:
            failed += 1
            continue
        if new is None:
            skipped += 1
            continue
        if not dry_run:
            _backend().put(key, new)
        done += 1
    return {"rewrapped": done, "already_current": skipped, "unreadable": failed, "dry_run": dry_run}
