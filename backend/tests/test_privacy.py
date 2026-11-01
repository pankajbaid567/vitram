"""Data export and account deletion."""

import json

import pytest
from sqlalchemy import inspect as sa_inspect

from app.db import Base, SessionLocal, engine
from app.models import AuditEvent, Document, User
from app.services import storage
from tests.conftest import signup

FORBIDDEN_KEYS = {"password_hash", "phone_enc", "phone_lookup", "file_key"}


def keys_anywhere(obj, found=None):
    found = set() if found is None else found
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.add(k)
            keys_anywhere(v, found)
    elif isinstance(obj, list):
        for v in obj:
            keys_anywhere(v, found)
    return found


def test_export_contains_the_users_data_and_no_secrets(sample):
    r = sample.get("/api/profile/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = json.loads(r.text)
    assert data["account"]["is_sample"] is True
    assert len(data["documents"]) == 5 and len(data["transactions"]) == 260
    assert data["document_facts"] and data["cards"] and data["emis"] and data["policies"] and data["consents"]
    assert not (keys_anywhere(data) & FORBIDDEN_KEYS), "secrets must never be exported"
    assert "scrypt$" not in r.text


def test_export_is_scoped_to_the_caller(sample, client):
    mine = json.loads(sample.get("/api/profile/export").text)
    signup(client)
    theirs = json.loads(client.get("/api/profile/export").text)
    assert theirs["transactions"] == [] and theirs["documents"] == []
    other_ids = {t["id"] for t in mine["transactions"]}
    assert not other_ids & {t["id"] for t in theirs["transactions"]}


def test_export_requires_sign_in(client):
    assert client.get("/api/profile/export").status_code == 401


def test_account_deletion_needs_confirmation_and_the_right_password(client):
    signup(client)
    assert client.post("/api/auth/account/delete", json={"password": "correct-horse-1"}).status_code == 422
    assert client.post("/api/auth/account/delete", json={"password": "wrong", "confirm": "DELETE"}).status_code == 403
    assert client.get("/api/auth/me").status_code == 200   # still there


def user_tables():
    return [t for t in Base.metadata.sorted_tables if any(fk.target_fullname == "users.id" for c in t.columns for fk in c.foreign_keys)]


def test_deleting_an_account_removes_every_row_and_every_file(client_factory):
    victim, bystander = client_factory(), client_factory()
    victim.post("/api/demo/workspace")
    bystander.post("/api/demo/workspace")
    # A sample workspace's documents are shared public fixtures, so it also holds one real upload: the thing erasure must remove.
    up = victim.post("/api/documents", data={"type": "bank_statement", "period_months": "6", "account_label": "Mine"},
                     files={"file": ("mine.csv", b"date,description,debit,credit,balance\n2026-01-01,MY OWN UPLOAD,10,,990\n", "text/csv")})
    assert up.status_code == 200, up.text
    me = victim.get("/api/auth/me").json()["id"]
    other = bystander.get("/api/auth/me").json()["id"]

    db = SessionLocal()
    all_keys = [d.file_key for d in db.query(Document).filter(Document.owner_user_id == me)]
    db.close()
    keys = [k for k in all_keys if not k.startswith(storage.SAMPLE_PREFIX)]
    assert len(keys) == 1 and len(all_keys) == 6 and all(storage.get(k) for k in all_keys)

    assert victim.post("/api/auth/account/delete", json={"confirm": "DELETE"}).status_code == 200  # sample workspaces have no password
    assert victim.get("/api/auth/me").status_code == 401

    with engine.connect() as conn:
        insp = sa_inspect(conn)
        for t in user_tables():
            col = "owner_user_id" if "owner_user_id" in {c["name"] for c in insp.get_columns(t.name)} else "user_id"
            left = conn.execute(t.select().where(t.c[col] == me)).fetchall()
            assert left == [], f"{t.name} still holds rows for the deleted user"
    for k in keys:
        with pytest.raises(Exception):  # noqa: B017 - any "not found" error is the point
            storage.get(k)

    db = SessionLocal()
    try:
        assert db.get(User, me) is None and db.get(User, other) is not None
        assert db.query(AuditEvent).filter(AuditEvent.user_id == me).count() == 0, "audit history is anonymised, not kept under the id"
        assert db.query(AuditEvent).filter(AuditEvent.action == "account.deleted").count() >= 1
    finally:
        db.close()
    assert len(bystander.get("/api/documents").json()) == 5   # someone else's data is untouched
