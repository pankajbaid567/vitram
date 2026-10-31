"""Vitt Saathi API (RD §11, §20: /ai/chat, /ai/session-token)."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.services.vision import provider_status
from app.db import get_db
from app.deps import current_user
from app.errors import DomainError, NotFound
from app.models import Conversation, Message, User
from app.services.saathi import context as C
from app.services.saathi import faq, orchestrator, prompts
from app.services.saathi import router_offline as ro
from app.services.saathi import tools as T

router = APIRouter(prefix="/ai", tags=["ai"])

ContextType = Literal["dashboard", "loan", "card", "emi", "insurance", "emergency", "document"]


def m_out(m: Message) -> dict:
    return {"id": m.id, "role": m.role, "content": m.content, "modality": m.modality, "mode": m.mode, "cards": m.cards or [],
            "citations": m.citations or [], "flags": [f for f in (m.flags or []) if not f.startswith("lang:")],
            "lang": next((f[5:] for f in (m.flags or []) if f.startswith("lang:")), None), "created_at": m.created_at.isoformat()}


def conv_out(db: Session, c: Conversation, ctx: dict | None = None) -> dict:
    msgs = db.query(Message).filter(Message.conversation_id == c.id).order_by(Message.created_at).all()
    return {"id": c.id, "context_type": c.context_type, "context_object_id": c.context_object_id,
            "context_label": (ctx or {}).get("label", C.CONTEXT_LABELS.get(c.context_type)),
            "messages": [m_out(m) for m in msgs[-60:]], "suggestions": ro.SUGGESTIONS.get(c.context_type, [])}


@router.get("/status")
def status(user: User = Depends(current_user)):
    s = get_settings()
    return {
        "assistant": "Vitt Saathi",
        "chat_mode": "gemini" if s.gemini_configured else "tool",
        "voice_available": s.gemini_live_configured,
        "vision": provider_status(),
        "chat_note": None if s.gemini_configured else
        "Tool mode — answers come from VITRAM's calculators and your data. Free-form AI is off because Gemini isn't configured.",
        "voice_note": None if s.gemini_live_configured else "Voice needs Gemini Live to be configured on the server.",
    }


@router.get("/faqs")
def faqs(category: Literal["cards", "insurance"] | None = None, user: User = Depends(current_user)):
    """Questions answered locally before any generative-AI call."""
    return {"faqs": faq.list_faqs(category), "count": len(faq.list_faqs(category))}


def _conversation(db: Session, user: User, cid: str | None, ctx: dict, channel: str = "web") -> Conversation:
    if cid:
        c = db.query(Conversation).filter(Conversation.id == cid, Conversation.user_id == user.id).first()
        if c and c.context_type == ctx["type"] and (c.context_object_id or None) == (ctx.get("object_id") or ctx.get("member_key") or None):
            return c
    c = Conversation(user_id=user.id, context_type=ctx["type"], context_object_id=ctx.get("object_id") or ctx.get("member_key"), channel=channel)
    db.add(c)
    db.flush()
    return c


@router.get("/conversations/latest")
def latest(context_type: ContextType = "dashboard", object_id: str | None = None, member_key: str | None = None,
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = C.resolve(db, user, context_type, object_id, member_key)
    key = object_id or member_key
    q = db.query(Conversation).filter(Conversation.user_id == user.id, Conversation.context_type == context_type)
    q = q.filter(Conversation.context_object_id == key) if key else q.filter(Conversation.context_object_id.is_(None))
    c = q.order_by(Conversation.started_at.desc()).first()
    if not c:
        return {"id": None, "context_type": context_type, "context_label": ctx["label"], "messages": [],
                "suggestions": ro.SUGGESTIONS.get(context_type, [])}
    return conv_out(db, c, ctx)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    context_type: ContextType = "dashboard"
    context_object_id: str | None = None
    member_key: str | None = None


@router.post("/chat")
def chat(body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = C.resolve(db, user, body.context_type, body.context_object_id, body.member_key)
    conv = _conversation(db, user, body.conversation_id, ctx)
    msg = orchestrator.handle_turn(db, user, conv, body.message.strip(), ctx)
    audit(db, user.id, "ai.chat", "conversation", conv.id, context=ctx["type"], mode=msg.mode)
    db.commit()
    return {"conversation_id": conv.id, "context_label": ctx["label"], "message": m_out(msg)}


class TokenIn(BaseModel):
    context_type: ContextType = "dashboard"
    context_object_id: str | None = None
    member_key: str | None = None
    conversation_id: str | None = None


@router.post("/session-token")
def session_token(body: TokenIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.saathi import gemini
    ctx = C.resolve(db, user, body.context_type, body.context_object_id, body.member_key)
    conv = _conversation(db, user, body.conversation_id, ctx, channel="voice")
    instruction = prompts.system_instruction(ctx, gemini.profile_slice_for(db, user, ctx)) if get_settings().gemini_live_configured else ""
    out = gemini.live_session_token(ctx, instruction)
    audit(db, user.id, "ai.voice_session", "conversation", conv.id, context=ctx["type"])
    db.commit()
    return {**out, "conversation_id": conv.id, "context_label": ctx["label"]}


class ToolIn(BaseModel):
    args: dict = Field(default_factory=dict)
    conversation_id: str
    context_type: ContextType = "dashboard"
    context_object_id: str | None = None
    member_key: str | None = None


@router.post("/tools/{name}")
def run_tool(name: str, body: ToolIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Executes a tool requested by the Live voice model so numbers still come from deterministic code."""
    ctx = C.resolve(db, user, body.context_type, body.context_object_id, body.member_key)
    conv = db.query(Conversation).filter(Conversation.id == body.conversation_id, Conversation.user_id == user.id).first()
    if not conv:
        raise NotFound("Conversation")
    expected_key = ctx.get("object_id") or ctx.get("member_key")
    if conv.context_type != ctx["type"] or (conv.context_object_id or None) != (expected_key or None):
        raise DomainError("CONTEXT_MISMATCH", "This conversation belongs to a different page context.", status_code=409)
    res = T.run(db, user, name, body.args, ctx)
    db.add(Message(conversation_id=conv.id, role="assistant", content="", modality="voice", mode="gemini",
                   cards=res.cards, citations=res.citations, tool_calls=[{"name": name, "args": body.args}]))
    audit(db, user.id, "ai.tool", "conversation", conv.id, tool=name)
    db.commit()
    return {"result": res.data, "cards": res.cards, "citations": res.citations}


class TranscriptIn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


@router.post("/conversations/{cid}/transcript")
def transcript(cid: str, body: TranscriptIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == cid, Conversation.user_id == user.id).first()
    if not conv:
        raise NotFound("Conversation")
    m = Message(conversation_id=conv.id, role=body.role, content=body.text, modality="voice", mode="gemini")
    db.add(m)
    db.commit()
    return m_out(m)
