"""Gemini adapter for Vitt Saathi chat and Live-voice session tokens.

STATUS: implemented against the `google-genai` Python SDK interface but NOT
verified in this environment — no GEMINI_API_KEY is configured (docs/spec/plan.md §7).
Model ids come only from configuration (GEMINI_MODEL / GEMINI_LIVE_MODEL);
nothing is hard-coded.
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import DomainError
from app.models import Conversation, Message, User
from app.services.saathi import prompts
from app.services.saathi import tools as T

log = logging.getLogger("vitram.gemini")
MAX_TOOL_STEPS = 5
LIVE_API_VERSION = "v1beta"
HISTORY_TURNS = 12
PROVIDER_COOLDOWN_SECONDS = 60
_provider_unavailable_until = 0.0


class GeminiUnavailable(Exception):
    pass


def _client(api_version: str | None = None):
    try:
        from google import genai
    except ImportError as exc:  # optional dependency: `uv sync --extra ai`
        raise GeminiUnavailable("google-genai package not installed") from exc
    s = get_settings()
    if not s.gemini_api_key:
        raise GeminiUnavailable("GEMINI_API_KEY not set")
    # The SDK otherwise retries transient 429/5xx responses up to five times
    # with exponential backoff. A busy provider can therefore leave the chat
    # request open for minutes. One bounded attempt lets the orchestrator use
    # its deterministic Tool-mode fallback promptly.
    http_options = {
        "timeout": max(10_000, s.gemini_timeout_ms),
        "retry_options": {"attempts": 1},
    }
    if api_version:
        http_options["api_version"] = api_version
    return genai.Client(api_key=s.gemini_api_key, http_options=http_options)


def function_declarations(context_type: str) -> list[dict]:
    return [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in T.allowed(context_type)]


def profile_slice_for(db: Session, user: User, ctx: dict) -> str:
    try:
        res = T.run(db, user, "profile_get_slice", {}, ctx) if "profile_get_slice" in T.CONTEXT_TOOLS.get(ctx["type"], []) else None
    except DomainError:
        res = None
    return json.dumps(res.data, default=str)[:4000] if res else ""


def run_turn(db: Session, user: User, conv: Conversation, text: str, ctx: dict) -> dict:
    global _provider_unavailable_until
    if time.monotonic() < _provider_unavailable_until:
        raise GeminiUnavailable("provider cooling down after a recent failure")

    from google.genai import types

    client = _client()
    s = get_settings()
    history = (db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.created_at.desc())
               .limit(HISTORY_TURNS).all())[::-1]
    contents = []
    for m in history:
        if m.role == "user" and m.content == text and m is history[-1]:
            continue
        contents.append(types.Content(role="user" if m.role == "user" else "model", parts=[types.Part(text=m.content)]))
    contents.append(types.Content(role="user", parts=[types.Part(text=text)]))
    config = types.GenerateContentConfig(
        system_instruction=prompts.system_instruction(ctx, profile_slice_for(db, user, ctx)),
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(name=d["name"], description=d["description"], parameters_json_schema=d["parameters"]) for d in function_declarations(ctx["type"])])],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )
    cards, cites, tool_log, tool_data = [], [], [], []
    try:
        for _ in range(MAX_TOOL_STEPS):
            # A model request may take longer than SQLite's busy timeout. Persist
            # the conversation (and any tool results) before waiting on the API
            # so other requests can write while this one is in flight.
            db.commit()
            resp = client.models.generate_content(model=s.gemini_model, contents=contents, config=config)
            calls = resp.function_calls or []
            if not calls:
                return {"text": (resp.text or "").strip() or "I don't have an answer for that.", "cards": cards,
                        "citations": cites, "tool_calls": tool_log, "tool_data": tool_data}
            contents.append(resp.candidates[0].content)
            parts = []
            for call in calls:
                args = dict(call.args or {})
                try:
                    r = T.run(db, user, call.name, args, ctx)
                    payload = r.data
                    cards += r.cards
                    cites += r.citations
                    tool_data.append(r.data)
                    tool_log.append({"name": call.name, "args": args})
                except DomainError as exc:
                    payload = {"error": exc.code, "message": exc.message}
                    tool_log.append({"name": call.name, "args": args, "error": exc.code})
                parts.append(types.Part.from_function_response(name=call.name, response={"result": json.loads(json.dumps(payload, default=str))}))
            contents.append(types.Content(role="user", parts=parts))
        return {"text": "I ran several calculations; the results are shown below.", "cards": cards, "citations": cites,
                "tool_calls": tool_log, "tool_data": tool_data}
    except GeminiUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 — network/API errors → graceful fallback (RD §26)
        # Avoid making every chat turn wait on a provider that just failed.
        # Tool mode remains fully functional during this short cooldown.
        _provider_unavailable_until = time.monotonic() + PROVIDER_COOLDOWN_SECONDS
        raise GeminiUnavailable(f"{type(exc).__name__}") from exc


def live_session_token(ctx: dict, system_instruction: str) -> dict:
    """Short-lived ephemeral token for a browser Live connection (RD §35.1)."""
    s = get_settings()
    if not s.gemini_live_configured:
        raise DomainError("INTEGRATION_NOT_CONFIGURED",
                          "Voice needs Gemini Live. Set GEMINI_API_KEY and GEMINI_LIVE_MODEL on the server.", status_code=503)
    # Official docs (checked 2026-09-23): ephemeral tokens work only with the Live API on API version v1beta.
    client = _client(LIVE_API_VERSION)
    now = datetime.now(timezone.utc)
    try:
        token = client.auth_tokens.create(config={
            "uses": 1,
            "expire_time": now + timedelta(minutes=30),
            "new_session_expire_time": now + timedelta(minutes=1),
            "http_options": {"api_version": LIVE_API_VERSION},
        })
    except Exception as exc:  # noqa: BLE001
        raise DomainError("VOICE_UNAVAILABLE", "Couldn't start a voice session right now. Use chat instead.", status_code=503) from exc
    return {
        "token": token.name,
        "model": s.gemini_live_model,
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "api_version": LIVE_API_VERSION,
        "system_instruction": system_instruction,
        "function_declarations": function_declarations(ctx["type"]),
    }
