"""Move all protected data onto the primary master key:  ``python -m app.rotate_keys [--dry-run]``.

Procedure (docs/SECURITY_MODEL.md): generate a new key; set it as VITRAM_DATA_KEY and put the old one in VITRAM_DATA_KEY_PREVIOUS; deploy;
run this; when it reports nothing unreadable, remove the old key. Safe to run repeatedly and while the API is serving: objects are re-wrapped
one at a time, and every reader accepts both the old and the new key until the old one is removed.
"""

import argparse
import json
import logging

from app.db import SessionLocal
from app.models import User
from app.security import decrypt_str, master_keys, phone_lookup_hash, rotate_str
from app.services import storage

log = logging.getLogger("vitram.rotate_keys")


def rotate_users(dry_run: bool = False) -> dict:
    """Phone numbers: re-encrypt under the primary key and recompute their keyed lookup hash."""
    db = SessionLocal()
    changed = unreadable = 0
    try:
        for user in db.query(User).filter(User.phone_enc.isnot(None)):
            try:
                phone = decrypt_str(user.phone_enc)
            except ValueError:
                unreadable += 1
                continue
            new_lookup = phone_lookup_hash(phone)
            if user.phone_lookup == new_lookup:
                try:
                    from app.security import fernet

                    fernet().decrypt(user.phone_enc.encode())
                    continue                                  # already on the primary key
                except Exception:  # noqa: BLE001 - not under the primary key: rotate it
                    pass
            if not dry_run:
                user.phone_enc, user.phone_lookup = rotate_str(user.phone_enc), new_lookup
            changed += 1
        if not dry_run:
            db.commit()
    finally:
        db.close()
    return {"phones_rotated": changed, "unreadable": unreadable, "dry_run": dry_run}


def run(dry_run: bool = False) -> dict:
    return {"master_keys": len(master_keys()), "files": storage.rotate_all(dry_run), "users": rotate_users(dry_run)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="count what would change; write nothing")
    args = ap.parse_args(argv)
    report = run(args.dry_run)
    print(json.dumps(report, indent=2))
    bad = report["files"]["unreadable"] + report["users"]["unreadable"]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
