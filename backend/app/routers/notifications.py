from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.errors import NotFound
from app.models import Notification, User

router = APIRouter(prefix="/notifications", tags=["notifications"])


def n_out(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
            "created_at": n.created_at.isoformat(), "read": n.read_at is not None}


@router.get("")
def list_notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50).all()
    return {"items": [n_out(n) for n in rows], "unread": sum(1 for n in rows if n.read_at is None)}


@router.post("/{nid}/read")
def mark_read(nid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == nid, Notification.user_id == user.id).first()
    if not n:
        raise NotFound("Notification")
    n.read_at = datetime.now(timezone.utc)
    db.commit()
    return n_out(n)


@router.post("/read-all")
def read_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    for n in db.query(Notification).filter(Notification.user_id == user.id, Notification.read_at.is_(None)):
        n.read_at = now
    db.commit()
    return {"ok": True}
