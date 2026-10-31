"""Security primitives: password hashing, tokens, encryption, phone handling and log redaction."""

import logging

import pytest
from app import security as sec


def test_passwords_are_salted_and_verify_only_the_right_one():
    a, b = sec.hash_password("correct-horse-1"), sec.hash_password("correct-horse-1")
    assert a != b, "salted: the same password hashes differently each time"
    assert a.startswith("scrypt$") and "correct-horse" not in a
    assert sec.verify_password("correct-horse-1", a) and not sec.verify_password("Correct-horse-1", a)


@pytest.mark.parametrize("stored", ["", "plaintext", "scrypt$only-two", "scrypt$!!!notbase64$!!!", "a$b$c$d"])
def test_malformed_stored_hashes_never_verify_and_never_raise(stored):
    assert sec.verify_password("anything", stored) is False


def test_session_tokens_are_random_and_only_their_hash_is_stored():
    (t1, id1), (t2, id2) = sec.new_session_token(), sec.new_session_token()
    assert t1 != t2 and id1 != id2 and len(t1) >= 32
    assert id1 == sec.token_id(t1) and id1 != t1 and len(id1) == 64


def test_encryption_round_trips_and_ciphertext_hides_the_content():
    blob = sec.encrypt_bytes(b"ARAVALI BANK statement")
    assert b"ARAVALI" not in blob and sec.decrypt_bytes(blob) == b"ARAVALI BANK statement"
    assert sec.decrypt_str(sec.encrypt_str("+919876543210")) == "+919876543210"
    assert sec.encrypt_str("x") != sec.encrypt_str("x"), "fresh nonce each time"
    with pytest.raises(ValueError, match="could not be decrypted"):
        sec.decrypt_bytes(blob[:-3] + b"abc")   # tampering is detected, not silently decrypted to garbage


@pytest.mark.parametrize("raw,expected", [
    ("9876543210", "+919876543210"), ("+91 98765 43210", "+919876543210"), ("09876543210", "+919876543210"),
    ("91-9876543210", "+919876543210"), ("5876543210", None), ("98765", None), ("", None), ("abcdefghij", None), ("+1 415 555 2671", None),
])
def test_indian_phone_normalisation(raw, expected):
    assert sec.normalize_indian_phone(raw) == expected


def test_phone_lookup_is_a_keyed_hash_not_the_number():
    h = sec.phone_lookup_hash("+919876543210")
    assert h == sec.phone_lookup_hash("+919876543210") and "9876543210" not in h and len(h) == 64
    assert h != sec.phone_lookup_hash("+919876543211")


def test_masking_shows_only_the_tail():
    assert sec.mask_phone("+919876543210") == "+91 ••••• 3210"
    assert sec.mask_tail("4111 1111 1111 4821") == "••••4821"
    assert sec.mask_tail("12") == "••12" and sec.mask_tail(None) is None and sec.mask_tail("") is None


@pytest.mark.parametrize("value,expected", [
    ("4111 1111 1111 1111", True), ("4111-1111-1111-1111", True), ("4111111111111111", True), ("my card is 5500 0000 0000 0004", True),
    ("4821", False), ("order 123456", False), ("", False),
])
def test_full_card_numbers_are_recognised(value, expected):
    assert sec.looks_like_full_card_number(value) is expected


def test_redaction_removes_phones_emails_and_card_numbers():
    out = sec.redact("call +91 98765 43210 or 9123456780, mail a.b+c@example.co.in, card 4111 1111 1111 1111")
    for leaked in ("98765", "9123456780", "a.b+c@example", "4111"):
        assert leaked not in out
    assert out.count("[redacted") == 4


def test_the_logging_filter_redacts_formatted_messages(caplog):
    f = sec.RedactingFilter()
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "user %s phoned %s", ("a@b.com", "9876543210"), None)
    assert f.filter(rec)
    assert "a@b.com" not in rec.getMessage() and "9876543210" not in rec.getMessage() and rec.args == ()
