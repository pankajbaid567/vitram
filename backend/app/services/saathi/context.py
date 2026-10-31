"""Context packages for Vitt Saathi (RD §11.1): the active page decides the
minimal data slice and tool permissions."""

from sqlalchemy.orm import Session

from app.errors import NotFound
from app.models import Document, Emi, FamilyMember, LoanProduct, User, UserCard, UserPolicy

CONTEXT_LABELS = {"dashboard": "General", "loan": "Loans", "card": "Credit cards", "emi": "EMIs",
                  "insurance": "Insurance", "emergency": "Emergency", "document": "Documents"}


def resolve(db: Session, user: User, context_type: str, object_id: str | None, member_key: str | None = None) -> dict:
    if context_type not in CONTEXT_LABELS:
        context_type = "dashboard"
    ctx = {"type": context_type, "object_id": object_id, "label": CONTEXT_LABELS[context_type], "member_key": member_key}
    if context_type == "insurance" and object_id:
        p = db.query(UserPolicy).filter(UserPolicy.id == object_id, UserPolicy.user_id == user.id).first()
        if not p:
            raise NotFound("Policy")
        ctx["label"] = f"Insurance · {p.product_name or 'Policy'}"
        ctx["document_ids"] = [p.document_id] if p.document_id else None
    elif context_type == "loan" and object_id:
        d = db.query(Document).filter(Document.id == object_id, Document.owner_user_id == user.id).first()
        if d:
            ctx["label"] = f"Loans · {d.display_name}"
            ctx["document_ids"] = [d.id]
        else:
            prod = db.get(LoanProduct, object_id)
            if not prod:
                raise NotFound("Loan")
            ctx["label"] = f"Loans · {prod.product_name}"
            ctx["product_id"] = prod.id
    elif context_type == "document":
        if not object_id:
            ctx.update(type="dashboard", label=CONTEXT_LABELS["dashboard"])
            return ctx
        d = db.query(Document).filter(Document.id == object_id, Document.owner_user_id == user.id).first()
        if not d:
            raise NotFound("Document")
        ctx["label"] = f"Documents · {d.display_name}"
        ctx["document_ids"] = [d.id]
        ctx["document_type"] = d.type
    elif context_type == "emi" and object_id:
        e = db.query(Emi).filter(Emi.id == object_id, Emi.user_id == user.id).first()
        if not e:
            raise NotFound("EMI")
        ctx["label"] = f"EMIs · {e.title}"
        if e.source_document_id:
            ctx["document_ids"] = [e.source_document_id]
    elif context_type == "card" and object_id:
        c = db.query(UserCard).filter(UserCard.id == object_id, UserCard.user_id == user.id).first()
        if not c:
            raise NotFound("Card")
        ctx["label"] = f"Credit cards · {c.nickname}"
    if context_type == "emergency":
        if member_key and member_key != "self":
            m = db.query(FamilyMember).filter(FamilyMember.id == member_key, FamilyMember.user_id == user.id).first()
            if not m:
                raise NotFound("Family member")
            ctx["label"] = f"Emergency · {m.name}"
            ctx["member_name"] = m.name
            # Only that person's policy documents are searchable (RD §16.1, §11.4)
            pols = db.query(UserPolicy).filter(UserPolicy.user_id == user.id).all()
            ctx["document_ids"] = [p.document_id for p in pols if m.id in [pm.family_member_id for pm in p.members] and p.document_id] or ["__none__"]
        elif member_key == "self":
            ctx["label"] = "Emergency · You"
            pols = db.query(UserPolicy).filter(UserPolicy.user_id == user.id).all()
            ctx["document_ids"] = [p.document_id for p in pols if None in [pm.family_member_id for pm in p.members] and p.document_id] or ["__none__"]
    return ctx
