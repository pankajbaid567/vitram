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

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        fake = self

        class _Pages:
            def paginate(self, Bucket, Prefix):
                keys = sorted(k for (b, k) in fake.objects if b == Bucket and k.startswith(Prefix))
                yield {"Contents": [{"Key": k} for k in keys[:2]]}      # two pages, to exercise pagination
                yield {"Contents": [{"Key": k} for k in keys[2:]]}

        return _Pages()


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


def test_s3_objects_can_be_listed_and_rotated_across_pages(s3, monkeypatch):
    from cryptography.fernet import Fernet

    from app import security
    from app.config import get_settings

    s = get_settings()
    old = s.vitram_data_key or security._load_key().decode()
    keys = [storage.put(f"object {i}".encode()) for i in range(5)]
    assert sorted(storage._backend().keys()) == sorted(keys)
    new_key = Fernet.generate_key().decode()
    monkeypatch.setattr(s, "vitram_data_key", new_key)
    monkeypatch.setattr(s, "vitram_data_key_previous", old)
    security._reset_caches()
    security._masters = None
    try:
        report = storage.rotate_all()
        assert report["rewrapped"] == 5 and report["unreadable"] == 0
        monkeypatch.setattr(s, "vitram_data_key_previous", None)          # retire the old key
        security._reset_caches()
        security._masters = None
        assert [storage.get(k) for k in keys] == [f"object {i}".encode() for i in range(5)]
    finally:
        monkeypatch.undo()
        security._reset_caches()
        security._masters = None


def test_sample_documents_are_served_from_bundled_fixtures_without_touching_storage(s3):
    from pathlib import Path

    fixture = (Path(__file__).resolve().parent.parent / "fixtures" / "sample_loan_kfs.pdf").read_bytes()
    key = storage.put_sample(fixture)
    assert key.startswith(storage.SAMPLE_PREFIX) and key.isalnum()
    assert not s3.objects                                   # nothing was written to the bucket
    assert storage.get(key) == fixture                      # and nothing is read from it
    storage.delete(key)                                     # shared, so deleting is a no-op
    assert storage.get(key) == fixture


def test_a_non_fixture_passed_to_put_sample_is_stored_normally(s3):
    key = storage.put_sample(b"not a bundled fixture")
    assert not key.startswith(storage.SAMPLE_PREFIX) and len(s3.objects) == 1
    assert storage.get(key) == b"not a bundled fixture"
