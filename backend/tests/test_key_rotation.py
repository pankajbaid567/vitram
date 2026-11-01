"""Envelope encryption and master-key rotation."""

import pytest
from cryptography.fernet import Fernet

from app import rotate_keys, security
from app.config import get_settings
from app.services import storage


@pytest.fixture
def keys(monkeypatch):
    """Switch the master keys and reset the cached ciphers; restore afterwards."""
    s = get_settings()
    original = (s.vitram_data_key, s.vitram_data_key_previous)

    def use(primary, previous=None):
        monkeypatch.setattr(s, "vitram_data_key", primary)
        monkeypatch.setattr(s, "vitram_data_key_previous", previous)
        security._reset_caches()
        security._masters = None

    yield use
    monkeypatch.setattr(s, "vitram_data_key", original[0])
    monkeypatch.setattr(s, "vitram_data_key_previous", original[1])
    security._reset_caches()
    security._masters = None


K1, K2, K3 = (Fernet.generate_key().decode() for _ in range(3))


def test_every_file_gets_its_own_data_key(keys):
    keys(K1)
    a, b = security.encrypt_bytes(b"same bytes"), security.encrypt_bytes(b"same bytes")
    assert a != b and a.startswith(security.ENVELOPE_MAGIC)
    assert security._split(a)[0] != security._split(b)[0]            # different wrapped DEKs
    assert security.decrypt_bytes(a) == security.decrypt_bytes(b) == b"same bytes"


def test_a_wrong_key_or_a_tampered_file_is_refused(keys):
    keys(K1)
    blob = security.encrypt_bytes(b"secret statement")
    keys(K2)
    with pytest.raises(ValueError):
        security.decrypt_bytes(blob)
    keys(K1)
    flipped = bytearray(blob)
    flipped[-3] ^= 1
    with pytest.raises(ValueError):
        security.decrypt_bytes(bytes(flipped))


def test_legacy_plain_fernet_objects_are_still_readable(keys):
    keys(K1)
    legacy = Fernet(K1.encode()).encrypt(b"written before envelopes")
    assert not legacy.startswith(security.ENVELOPE_MAGIC)
    assert security.decrypt_bytes(legacy) == b"written before envelopes"


def test_rotation_rewraps_only_the_header_and_keeps_the_body_bytes(keys):
    keys(K1)
    old = security.encrypt_bytes(b"x" * 5000)
    keys(K2, K1)
    assert security.decrypt_bytes(old) == b"x" * 5000                 # old key still accepted during the transition
    new = security.rewrap(old)
    assert new is not None and security._split(new)[1] == security._split(old)[1]   # encrypted body untouched
    assert security.rewrap(new) is None                               # already on the primary key
    keys(K2)                                                           # retire K1 entirely
    assert security.decrypt_bytes(new) == b"x" * 5000
    with pytest.raises(ValueError):
        security.decrypt_bytes(old)


def test_legacy_blobs_are_upgraded_to_envelopes_on_rotation(keys):
    keys(K1)
    legacy = Fernet(K1.encode()).encrypt(b"old format")
    keys(K2, K1)
    upgraded = security.rewrap(legacy)
    assert upgraded.startswith(security.ENVELOPE_MAGIC)
    keys(K2)
    assert security.decrypt_bytes(upgraded) == b"old format"


def test_a_two_step_rotation_chain(keys):
    keys(K1)
    blob = security.encrypt_bytes(b"data")
    keys(K2, K1)
    blob = security.rewrap(blob)
    keys(K3, f"{K2},{K1}")
    blob = security.rewrap(blob)
    keys(K3)
    assert security.decrypt_bytes(blob) == b"data"


def test_rotate_keys_command_moves_every_stored_file(keys, client_factory, tmp_path, monkeypatch):   # client_factory boots the schema
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)       # an isolated object store: other tests leave blobs under other keys
    keys(K1)
    ids = [storage.put(f"document {i}".encode() * 100) for i in range(5)]
    path = storage._backend()._path(ids[0])
    path.write_bytes(Fernet(K1.encode()).encrypt(b"a legacy document"))   # one object in the old format
    keys(K2, K1)
    dry = rotate_keys.run(dry_run=True)
    assert dry["files"]["rewrapped"] >= 5 and dry["files"]["unreadable"] == 0
    assert path.read_bytes().startswith(b"gAAAA")                         # a dry run changes nothing
    report = rotate_keys.run()
    assert report["files"]["rewrapped"] >= 5 and report["files"]["unreadable"] == 0
    assert rotate_keys.run()["files"]["rewrapped"] == 0                   # idempotent
    keys(K2)                                                               # drop the old key: everything must still open
    assert storage.get(ids[0]) == b"a legacy document"
    assert all(storage.get(i).startswith(b"document") for i in ids[1:])


def test_phone_numbers_survive_rotation_including_the_lookup_hash(keys, client):
    from app.db import SessionLocal
    from app.models import User
    from tests.conftest import signup

    keys(K1)
    me = signup(client)
    client.patch("/api/onboarding/about", json={"phone": "9876543210"})
    db = SessionLocal()
    user = db.query(User).filter(User.email == me["email"]).one()
    old_lookup = user.phone_lookup
    keys(K2, K1)
    assert security.phone_lookup_hash("+919876543210") != old_lookup
    assert old_lookup in security.phone_lookup_candidates("+919876543210")      # inbound matching works mid-rotation
    assert rotate_keys.rotate_users()["phones_rotated"] >= 1
    db.expire_all()
    user = db.query(User).filter(User.email == me["email"]).one()
    assert user.phone_lookup == security.phone_lookup_hash("+919876543210")
    keys(K2)
    assert security.decrypt_str(user.phone_enc) == "+919876543210"
    db.close()
