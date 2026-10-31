"""Both storage backends keep the same contract: ciphertext at rest, random keys, safe key handling."""

import io

import pytest

from app.services import storage


class FakeS3:
    """Just enough of boto3's S3 client for the adapter."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


@pytest.fixture
def s3(monkeypatch):
    fake = FakeS3()
    storage._backend.cache_clear()
    monkeypatch.setattr(storage, "_backend", lambda: storage._S3Backend(fake, "vault"))
    return fake


def test_s3_round_trip_stores_only_ciphertext(s3):
    key = storage.put(b"salary slip, account 1234")
    (bucket, object_key), blob = next(iter(s3.objects.items()))
    assert bucket == "vault" and object_key == f"objects/{key}.bin"
    assert b"salary slip" not in blob                     # encrypted before it leaves the process
    assert storage.get(key) == b"salary slip, account 1234"


def test_s3_delete_removes_the_object_and_is_repeatable(s3):
    key = storage.put(b"x")
    storage.delete(key)
    assert not s3.objects
    storage.delete(key)                                    # deleting twice is fine


def test_unsafe_keys_never_reach_either_backend(s3):
    with pytest.raises(ValueError):
        storage.get("../../etc/passwd")
    storage.delete("../escape")                            # ignored, no exception
    assert not s3.objects


def test_s3_backend_needs_complete_settings(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    get_settings.cache_clear()
    storage._backend.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="S3_ENDPOINT_URL"):
            storage._backend()
    finally:
        monkeypatch.delenv("STORAGE_BACKEND")
        get_settings.cache_clear()
        storage._backend.cache_clear()


def test_unknown_backend_is_refused(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("STORAGE_BACKEND", "tape")
    get_settings.cache_clear()
    storage._backend.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="Unknown STORAGE_BACKEND"):
            storage._backend()
    finally:
        monkeypatch.delenv("STORAGE_BACKEND")
        get_settings.cache_clear()
        storage._backend.cache_clear()
