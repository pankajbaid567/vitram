"""Vitt Saathi orchestration (RD §11, §18.2).

User message → resolve context → minimal profile slice → tools (allow-listed)
→ validate tool output + provenance → explanation → cards + sources.
Gemini is used when configured; otherwise the labelled Tool mode runs.
"""

import logging
import re
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import DomainError
from app.models import Conversation, FamilyMember, Message, User
from app.services.saathi import faq, i18n
from app.services.saathi import replies
from app.services.saathi import router_offline as ro
from app.services.saathi import tools as T

log = logging.getLogger("vitram.saathi")


# --- numeric fidelity guard (RD §27.3) ---------------------------------------

def _numbers(obj, out: set[Decimal]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(Decimal(str(obj)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers(v, out)
    elif isinstance(obj, str):
        for m in re.finditer(r"₹\s?([\d,]+(?:\.\d+)?)", obj):
            out.add(Decimal(m.group(1).replace(",", "")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fidelity_flags(text: str, sources: list) -> list[str]:
    allowed: set[Decimal] = set()
    for s in sources:
        _numbers(s, allowed)
    flags = []
    for m in re.finditer(r"₹\s?([\d,]+(?:\.\d+)?)", text):
        raw = m.group(1).replace(",", "")
        value = Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # A whole-rupee claim may be a displayed rounding of a paise value.
        # A claim with paise must match the tool output exactly to the paise.
        match = any(
            value == (a.quantize(Decimal("1"), rounding=ROUND_HALF_UP) if "." not in raw else a)
            for a in allowed
        )
        if not match:
            flags.append(f"unverified_amount:{raw}")
    return flags


# --- Tool mode ---------------------------------------------------------------

def _pending(db: Session, conv: Conversation) -> dict:
    last = (db.query(Message).filter(Message.conversation_id == conv.id, Message.role == "assistant")
            .order_by(Message.created_at.desc()).first())
    if last and last.tool_calls:
        for tc in last.tool_calls:
            if "pending" in tc:
                return tc["pending"]
    return {}


def _last_card(db: Session, conv: Conversation, card_type: str) -> dict | None:
    for m in db.query(Message).filter(Message.conversation_id == conv.id, Message.role == "assistant").order_by(Message.created_at.desc()).limit(10):
        for c in m.cards or []:
            if c.get("type") == card_type:
                return c
    return None


def _member_key(db: Session, user: User, relation: str | None) -> str | None:
    if relation is None:
        return None
    if relation == "self":
        return "self"
    fam = db.query(FamilyMember).filter(FamilyMember.user_id == user.id).all()
    match = [m for m in fam if m.relation == relation]
    return match[0].id if len(match) == 1 else None


def conversation_language(db: Session, user: User, conv: Conversation, text: str) -> str:
    """Language of this turn: the message itself, else the conversation's last clear language, else the user's preference."""
    lang = i18n.detect(text)
    if lang:
        return lang
    for m in (db.query(Message).filter(Message.conversation_id == conv.id, Message.role == "user")
              .order_by(Message.created_at.desc()).limit(6)):
        prev = i18n.detect(m.content)
        if prev:
            return prev
    return user.preferred_language if user.preferred_language in i18n.LANGS else "en"


_SUMMARY = re.compile(r"summar|what (?:did|does|was|is) (?:it|this|vitram)|what.*(?:found|read|extract)|overview|key (?:details|points)|"
                      r"kya (?:mila|likha|hai is)|samjhao|सार|क्या मिला|क्या लिखा|समझाइए", re.I)


def tool_mode(db: Session, user: User, conv: Conversation, text: str, ctx: dict, lang: str | None = None) -> dict:
    text = i18n.normalize(text)
    lang = lang or conversation_language(db, user, conv, text)
    pending = _pending(db, conv)
    intent = ro.detect_intent(text)
    ctype = ctx["type"]
    if pending.get("intent") and intent in (None, "loan_search", "emergency", "card_best", "insurance_find") :
        intent = pending["intent"] if intent is None else intent
    calls: list[tuple[str, dict]] = []
    ask = None

    if ctype == "document":
        # One document is open: summarise it, or look up the question in its own text. Nothing else is reachable here.
        if not text.strip() or _SUMMARY.search(text):
            calls.append(("document_summary", {}))
        else:
            calls.append(("documents_search", {"query": text}))
    elif intent == "emergency" or (ctype == "emergency" and intent in (None, "doc_question")):
        rel = ro.parse_relation(text)
        member = ctx.get("member_key") or _member_key(db, user, rel) or pending.get("member_key")
        if intent == "emergency" or ctype == "emergency":
            if intent == "doc_question" and ctype == "emergency":
                calls.append(("documents_search", {"query": text}))
            else:
                calls.append(("insurance_find_applicable_existing", {"member_key": member, "event": ro.parse_event(text)}))
    elif intent == "consult":
        calls.append(("consultation_request", {"topic": text[:200], "policy_id": ctx.get("object_id") if ctype == "insurance" else None,
                                               "member_key": ctx.get("member_key")}))
    elif intent == "card_best" or (ctype == "card" and ro.parse_amount(text) and intent is None):
        amount = ro.parse_amount(text) or pending.get("amount")
        cat, merchant = ro.parse_card_category(text)
        cat = cat or pending.get("category")
        if not amount:
            ask = {"text": i18n.t(lang, "ask_card"),
                   "pending": {"intent": "card_best", "category": cat}}
        else:
            calls.append(("cards_best_for_spend", {"amount": amount, "category": cat, "merchant": merchant}))
    elif intent == "cards_list":
        calls.append(("cards_list", {}))
    elif intent == "reminder":
        calls.append(("reminders_create", {}))
    elif intent in ("loan_cost", "compare", "prepay", "missed", "rate_change", "tenure") and ctype in ("loan", "dashboard"):
        last = _last_card(db, conv, "loan_options")
        product_id = ctx.get("product_id") or (last["results"][0]["product_id"] if last and last.get("results") else None)
        loan_ctx = last["intent"] if last else {}
        doc_loan = None
        if ctx.get("document_ids") and ctype == "loan":
            from app.models import UserLoan
            doc_loan = db.query(UserLoan).filter(UserLoan.source_document_id == ctx["document_ids"][0]).first()
        base = {"user_loan_id": doc_loan.id} if doc_loan else ({"product_id": product_id, "principal": loan_ctx.get("amount"),
                                                                 "tenure_months": (last["results"][0]["tenure_months"] if last and last.get("results") else None)}
                                                                if product_id else None)
        if base is None or (not doc_loan and not base.get("principal")):
            ask = {"text": i18n.t(lang, "ask_loan_first"),
                   "pending": {"intent": "loan_search"}}
        elif intent == "compare":
            if last and len(last.get("results", [])) >= 2:
                ids = [r["product_id"] for r in last["results"][:3]]
                calls.append(("loans_compare", {"product_ids": ids, "purpose": loan_ctx["purpose"], "amount": loan_ctx["amount"],
                                                "tenure_months": loan_ctx.get("tenure_months")}))
            else:
                ask = {"text": i18n.t(lang, "ask_compare_two")}
        elif intent == "loan_cost":
            calls.append(("finance_loan_cost", base))
        elif intent == "prepay":
            amt = ro.parse_amount(text)
            after = ro.parse_tenure(text) or 12
            if not amt:
                ask = {"text": i18n.t(lang, "ask_prepay")}
            else:
                calls.append(("finance_loan_what_if", {**base, "kind": "prepayment", "prepay_amount": amt, "after_month": after,
                                                       "mode": "reduce_emi" if re.search(r"emi (?:kam|reduce|lower)|lower (?:the )?emi|reduce emi", text.lower()) else "reduce_tenure"}))
        elif intent == "missed":
            calls.append(("finance_loan_what_if", {**base, "kind": "missed_payment", "days_late": ro.parse_days(text) or 30}))
        elif intent == "rate_change":
            r = ro.parse_rate(text)
            if r is None:
                ask = {"text": i18n.t(lang, "ask_rate")}
            else:
                calls.append(("finance_loan_what_if", {**base, "kind": "rate_change", "new_rate_pct": r}))
        else:
            n = ro.parse_tenure(text)
            if not n:
                ask = {"text": i18n.t(lang, "ask_tenure")}
            else:
                calls.append(("finance_loan_what_if", {**base, "kind": "tenure_change", "new_tenure_months": n}))
    elif intent in ("missed", "prepay", "rate_change") and ctype == "emi":
        scenario = {"missed": "missed_payment", "prepay": "prepayment", "rate_change": "rate_change"}[intent]
        args = {"scenario": scenario, "emi_id": ctx.get("object_id")}
        if re.search(r"late|der|delay", text.lower()) and intent == "missed":
            args.update(scenario="late_payment", days_late=ro.parse_days(text) or 15)
        if scenario == "prepayment":
            args["prepay_amount"] = ro.parse_amount(text)
            if not args["prepay_amount"]:
                ask = {"text": i18n.t(lang, "ask_prepay_amount")}
        if scenario == "rate_change":
            args["new_rate_pct"] = ro.parse_rate(text)
            if args["new_rate_pct"] is None:
                ask = {"text": i18n.t(lang, "ask_rate")}
        if not ask:
            calls.append(("finance_emi_what_if", args))
    elif intent == "emis":
        calls.append(("emis_list", {}))
    elif intent == "insurance_find" or (ctype == "insurance" and intent is None and ro.insurance_type(text)):
        itype = ro.insurance_type(text) or pending.get("type") or "health"
        rel = ro.parse_relation(text)
        keys = []
        if re.search(r"parents?|mother and father|mummy papa", text.lower()):
            keys = [k for k in (_member_key(db, user, "mother"), _member_key(db, user, "father")) if k]
        elif rel:
            k = _member_key(db, user, rel)
            keys = [k] if k else []
        if not keys:
            keys = ["self"]
        calls.append(("insurance_search", {"type": itype, "member_keys": keys, "sum_insured": ro.parse_amount(text)}))
    elif intent == "doc_question" and ctype in ("insurance", "loan", "emi", "emergency"):
        calls.append(("documents_search", {"query": text}))
    elif intent == "doc_question":
        calls.append(("navigation_open", {"destination": "insurance"}))
    elif intent == "loan_search" or pending.get("intent") == "loan_search":
        slots = {**{k: v for k, v in pending.items() if k != "intent"}}
        for k, v in (("purpose", ro.parse_purpose(text)), ("amount", ro.parse_amount(text)), ("tenure_months", ro.parse_tenure(text)),
                     ("collateral", ro.parse_collateral(text))):
            if v is not None:
                slots[k] = v
        if not slots.get("purpose"):
            ask = {"text": i18n.t(lang, "ask_purpose"),
                   "pending": {"intent": "loan_search", **slots},
                   "quick": ["Personal need", "Vehicle", "Home", "Education", "Medical"]}
        elif not slots.get("amount"):
            ask = {"text": i18n.t(lang, "ask_amount"), "pending": {"intent": "loan_search", **slots}}
        elif slots["purpose"] in ("home", "vehicle") and "collateral" not in slots and slots["purpose"] != "vehicle":
            ask = {"text": i18n.t(lang, "ask_home_collateral"),
                   "pending": {"intent": "loan_search", **slots, "collateral": "property"}, "quick": ["Yes", "No"]}
        else:
            if slots.get("collateral") is None and slots["purpose"] == "vehicle":
                slots["collateral"] = "vehicle"
            calls.append(("loans_search", {k: v for k, v in slots.items() if k in ("purpose", "amount", "tenure_months", "collateral")}))
    elif intent == "profile":
        calls.append(("profile_get_slice", {}))
    elif intent == "loan_cost" and ctype == "emi":
        calls.append(("emis_list", {}))

    if pending.get("intent") == "loan_search" and ask is None and not calls and re.fullmatch(r"\s*(yes|haan|ha|ok)\s*", text.lower()):
        calls.append(("loans_search", {k: v for k, v in pending.items() if k in ("purpose", "amount", "tenure_months", "collateral")}))

    if ask:
        return {"text": ask["text"], "cards": [{"type": "quick_replies", "options": ask["quick"]}] if ask.get("quick") else [],
                "citations": [], "tool_calls": [{"pending": ask.get("pending", {})}] if ask.get("pending") else []}
    if not calls:
        sugg = {"hi": i18n.SUGGESTIONS_HI, "hinglish": i18n.SUGGESTIONS_HINGLISH}.get(lang, ro.SUGGESTIONS).get(ctype, [])
        return {"text": i18n.t(lang, f"help_{ctype}" if f"help_{ctype}" in i18n.TEXT else "help_dashboard"),
                "cards": [{"type": "quick_replies", "options": sugg}],
                "citations": [], "tool_calls": []}

    cards, cites, tool_log, parts = [], [], [], []
    for name, args in calls:
        if name not in T.CONTEXT_TOOLS.get(ctype, []):
            # Cross-module request: offer navigation instead of silently loading unrelated data (RD §11.4).
            dest = {"loans_search": "explore_loans", "cards_best_for_spend": "card_optimizer", "insurance_search": "explore_insurance",
                    "insurance_find_applicable_existing": "emergency", "finance_emi_what_if": "emis", "emis_list": "emis",
                    "documents_search": "documents", "consultation_request": "consult"}.get(name, "loans")
            res = T.run(db, user, "navigation_open", {"destination": dest}, ctx) if "navigation_open" in T.CONTEXT_TOOLS.get(ctype, []) else None
            parts.append(i18n.t(lang, "other_screen"))
            if res:
                cards += res.cards
            continue
        try:
            res = T.run(db, user, name, args, ctx)
        except DomainError as exc:
            parts.append(exc.message)
            tool_log.append({"name": name, "args": args, "error": exc.code})
            continue
        cards += res.cards
        cites += res.citations
        tool_log.append({"name": name, "args": args})
        parts.append(replies.compose(name, res.data, ctx, lang))
        if res.data.get("needs"):
            tool_log.append({"pending": {"intent": "emergency" if name.startswith("insurance_find") else None}})
    return {"text": " ".join(p for p in parts if p), "cards": cards, "citations": cites, "tool_calls": tool_log}


# --- entry point ----------------------------------------------------------------

def handle_turn(db: Session, user: User, conv: Conversation, text: str, ctx: dict, modality: str = "text") -> Message:
    db.add(Message(conversation_id=conv.id, role="user", content=text, modality=modality))
    db.flush()
    settings = get_settings()
    lang = conversation_language(db, user, conv, i18n.normalize(text))
    ctx = {**ctx, "lang": lang}
    mode = "tool"
    flags: list[str] = []
    faq_hit = faq.answer(i18n.normalize(text), lang) or faq.product_answer(db, text)
    result = None if not faq_hit else {
        "text": faq_hit["text"], "cards": [], "citations": [],
        "tool_calls": [{"name": "faq_lookup", "args": {"id": faq_hit["id"]}}],
    }
    if settings.gemini_configured and result is None:
        from app.services.saathi import gemini
        try:
            result = gemini.run_turn(db, user, conv, text, ctx)
            mode = "gemini"
        except gemini.GeminiUnavailable as exc:
            log.warning("Gemini unavailable, falling back to tool mode: %s", exc)
            flags.append("ai_unavailable")
    if result is None:
        result = tool_mode(db, user, conv, text, ctx, lang)
    if mode == "gemini":
        sources = [c for c in result["cards"]] + [result.get("tool_data", [])]
        flags += fidelity_flags(result["text"], sources)
        if any(f.startswith("unverified_amount:") for f in flags):
            result["text"] = "I couldn't verify every amount in that answer. Use the calculated results below as the source of truth."
    msg = Message(conversation_id=conv.id, role="assistant", content=result["text"], modality="text", mode=mode,
                  cards=result["cards"], citations=_dedupe(result["citations"]), tool_calls=result["tool_calls"],
                  flags=flags + [f"lang:{lang}"])
    db.add(msg)
    db.commit()
    return msg


def _dedupe(cites: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in cites:
        k = (c.get("document_id"), c.get("page"), c.get("fact_key"), (c.get("snippet") or "")[:40])
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out[:12]
