"""Credit Card Intelligence (RD §13, S20–S22)."""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import current_user
from app.errors import DomainError, NotFound
from app.models import CalculationRun, CardProduct, Document, FinancialProfile, User, UserCard
from app.security import looks_like_full_card_number
from app.services import profile_engine
from app.services.card_import import apply_reviewed
from app.services.catalogue import catalogue_meta
from app.services.finance.rewards import FORMULA_VERSION, best_for_spend, estimate_card
from app.services.statements.categorizer import CATEGORIES, categorize

router = APIRouter(prefix="/cards", tags=["cards"])

SPEND_CATEGORIES = ["travel", "food_delivery", "groceries", "ecommerce", "fuel", "utilities", "entertainment",
                    "healthcare", "education", "subscriptions", "rent", "insurance", "other"]


class Expiring(BaseModel):
    amount: float = Field(gt=0)
    date: date


class CardIn(BaseModel):
    catalogue_id: str | None = None
    nickname: str = Field(min_length=1, max_length=60)
    last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    credit_limit: float | None = Field(default=None, ge=0)
    outstanding: float | None = Field(default=None, ge=0)
    due_date: date | None = None
    points_balance: float | None = Field(default=None, ge=0)
    points_as_of: date | None = None
    expiring: list[Expiring] = Field(default_factory=list, max_length=10)
    cycle_spend: dict[str, float] = Field(default_factory=dict)
    # Benefits the user knows about (lounge access, fuel waiver…). Shown as "You entered", separate from catalogue terms.
    user_benefits: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("user_benefits")
    @classmethod
    def _benefits(cls, v: list[str]) -> list[str]:
        out = []
        for b in v:
            b = (b or "").strip()
            if not b:
                continue
            if len(b) > 120:
                raise ValueError("Keep each benefit under 120 characters.")
            if looks_like_full_card_number(b):
                raise ValueError("Don't enter card numbers. VITTRM only needs the last 4 digits.")
            out.append(b)
        return out

    @field_validator("nickname")
    @classmethod
    def _no_pan(cls, v: str) -> str:
        if looks_like_full_card_number(v):
            raise ValueError("Don't enter your full card number. VITTRM only needs the last 4 digits.")
        return v.strip()

    @field_validator("cycle_spend")
    @classmethod
    def _cats(cls, v: dict) -> dict:
        bad = [k for k in v if k not in CATEGORIES]
        if bad:
            raise ValueError(f"Unknown category: {bad[0]}")
        return {k: float(x) for k, x in v.items() if x is not None and x >= 0}


def _card_dict(c: UserCard) -> dict:
    return {"id": c.id, "name": c.nickname, "rules": (c.catalogue.data.get("rules") if c.catalogue else None),
            "cycle_spend": c.cycle_spend or {}}


def card_out(c: UserCard) -> dict:
    cat = c.catalogue
    data = cat.data if cat else {}
    rules = data.get("rules") or {}
    return {
        "id": c.id, "nickname": c.nickname, "last4": c.last4, "masked": f"•••• {c.last4}" if c.last4 else None,
        "catalogue_id": c.catalogue_id, "issuer": cat.issuer if cat else None, "card_name": cat.card_name if cat else None,
        "network": data.get("network"), "credit_limit": c.credit_limit, "outstanding": c.outstanding,
        "due_date": c.due_date.isoformat() if c.due_date else None,
        "annual_fee": (data.get("fees") or {}).get("annual"), "fees": data.get("fees"),
        "reward_currency": rules.get("reward_currency"), "reward_unit": rules.get("currency_name"),
        "points": c.points, "cycle_spend": c.cycle_spend or {}, "user_benefits": c.user_benefits or [],
        "has_rules": bool(rules), "catalogue": catalogue_meta(cat) if cat else None,
        "source_document_id": c.source_document_id,
        "source_fields": c.source_fields or [],
        "data_source": ("You confirmed balances and dues from an uploaded card document; reward rules come from the sample catalogue"
                        if c.source_document_id and cat else "You confirmed balances and dues from an uploaded card document"
                        if c.source_document_id else "You entered balances and dues; reward rules come from the sample catalogue"
                        if cat else "You entered this card; no reward rules available"),
    }


def _get(db: Session, user: User, card_id: str) -> UserCard:
    c = db.query(UserCard).filter(UserCard.id == card_id, UserCard.user_id == user.id).first()
    if not c:
        raise NotFound("Card")
    return c


@router.get("/catalogue")
def catalogue(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"products": [{"id": r.id, "issuer": r.issuer, "card_name": r.card_name, "network": r.data.get("network"),
                          "annual_fee": (r.data.get("fees") or {}).get("annual"),
                          "reward_unit": (r.data.get("rules") or {}).get("currency_name"),
                          "categories": r.data.get("categories", []), "best_for": r.data.get("best_for", []),
                          "official_url": r.data.get("official_url"), "reference_only": r.data.get("reference_only", False),
                          "catalogue": catalogue_meta(r)}
                         for r in db.query(CardProduct).order_by(CardProduct.issuer)]}


@router.get("/explore")
def explore_cards(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Sample new-card discovery; spending relevance is not issuer eligibility or approval."""
    profile = db.get(FinancialProfile, user.id)
    categories = (profile.profile.get("expense_summary", {}).get("category_totals", []) if profile and profile.profile else [])
    spend = {row["category"]: row["monthly_avg"] for row in categories if row.get("monthly_avg", 0) > 0}
    products = []
    for card in db.query(CardProduct).order_by(CardProduct.issuer).all():
        rules = card.data.get("rules") or {}
        matched = sorted({category for rule in rules.get("category_rules", [])
                          for category in rule.get("categories", []) if spend.get(category, 0) > 0},
                         key=lambda category: -spend[category])
        products.append({
            "id": card.id, "issuer": card.issuer, "card_name": card.card_name,
            "fees": card.data.get("fees"), "reward_currency": rules.get("currency_name"),
            "category_rules": rules.get("category_rules", []), "exclusions": rules.get("exclusions", {}),
            "benefits": rules.get("benefits", []), "redemption": card.data.get("redemption", []),
            "matched_spend_categories": [{"category": category, "label": CATEGORIES.get(category, category),
                                          "monthly_avg": spend[category]} for category in matched],
            "eligibility": "unknown", "categories": card.data.get("categories", []),
            "best_for": card.data.get("best_for", []), "official_url": card.data.get("official_url"),
            "reference_only": card.data.get("reference_only", False), "catalogue": catalogue_meta(card),
        })
    return {"currency": "INR", "products": products,
            "notice": "Market reference entries help discovery. Only products with verified rules are used for reward calculations. Check the issuer's current terms before applying."}


@router.get("")
def list_cards(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cards = db.query(UserCard).filter(UserCard.user_id == user.id).order_by(UserCard.created_at).all()
    totals: dict[str, float] = {}
    for c in cards:
        if c.points and c.points.get("balance") is not None:
            unit = (c.catalogue.data.get("rules", {}).get("currency_name") if c.catalogue else None) or "points"
            totals[unit] = totals.get(unit, 0) + c.points["balance"]
    expiring = []
    for c in cards:
        for e in (c.points or {}).get("expiring", []):
            expiring.append({"card_id": c.id, "card": c.nickname, "amount": e["amount"], "date": e["date"],
                             "unit": (c.catalogue.data.get("rules", {}).get("currency_name") if c.catalogue else "points")})
    expiring.sort(key=lambda e: e["date"])
    return {"currency": "INR", "cards": [card_out(c) for c in cards],
            "reward_totals": [{"unit": u, "balance": b} for u, b in totals.items()],
            "reward_totals_note": "Balances are shown per reward currency because different programmes aren't worth the same.",
            "expiring": expiring, "categories": [{"key": k, "label": CATEGORIES[k]} for k in SPEND_CATEGORIES]}


def _apply(c: UserCard, body: CardIn, db: Session) -> None:
    if body.catalogue_id and not db.get(CardProduct, body.catalogue_id):
        raise DomainError("UNKNOWN_CARD", "That card programme isn't in the catalogue.", field="catalogue_id")
    c.catalogue_id = body.catalogue_id
    c.nickname, c.last4 = body.nickname, body.last4
    c.credit_limit, c.outstanding, c.due_date = body.credit_limit, body.outstanding, body.due_date
    c.points = None if body.points_balance is None else {
        "balance": body.points_balance, "as_of": (body.points_as_of or date.today()).isoformat(),
        "expiring": [{"amount": e.amount, "date": e.date.isoformat()} for e in body.expiring], "source": "user",
    }
    c.cycle_spend = body.cycle_spend
    c.user_benefits = body.user_benefits
    # A manual edit supersedes the old document snapshot; its imported figures
    # must never be silently cleared when that document is later reprocessed.
    c.source_document_id = None
    c.source_fields = None


class CardImportIn(BaseModel):
    document_id: str
    replace_existing: bool = False


@router.post("/{card_id}/import-document")
def import_card_document(card_id: str, body: CardImportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    card = _get(db, user, card_id)
    doc = db.query(Document).filter(Document.id == body.document_id, Document.owner_user_id == user.id).first()
    if not doc:
        raise NotFound("Document")
    imported = apply_reviewed(db, doc, card, replace_existing=body.replace_existing)
    audit(db, user.id, "card.document_imported", "card", card.id, document_id=doc.id, fields=imported)
    profile_engine.build_profile(db, user)
    db.commit()
    return {"card": card_out(card), "imported_fields": imported}


@router.post("")
def add_card(body: CardIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.query(UserCard).filter(UserCard.user_id == user.id).count() >= 12:
        raise DomainError("LIMIT", "You can add up to 12 cards.")
    c = UserCard(user_id=user.id)
    _apply(c, body, db)
    db.add(c)
    db.flush()
    db.refresh(c)
    audit(db, user.id, "card.added", "card", c.id)
    profile_engine.build_profile(db, user)
    db.commit()
    return card_out(c)


@router.patch("/{card_id}")
def update_card(card_id: str, body: CardIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get(db, user, card_id)
    _apply(c, body, db)
    db.flush()
    db.refresh(c)
    profile_engine.build_profile(db, user)
    db.commit()
    return card_out(c)


@router.delete("/{card_id}")
def delete_card(card_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get(db, user, card_id)
    db.delete(c)
    audit(db, user.id, "card.deleted", "card", card_id)
    profile_engine.build_profile(db, user)
    db.commit()
    return {"ok": True}


def _spend_profile(db: Session, user: User) -> dict[str, float]:
    p = profile_engine.get_profile(db, user)
    return {c["category"]: c["monthly_avg"] for c in p.get("expense_summary", {}).get("category_totals", [])
            if c["category"] in SPEND_CATEGORIES}


@router.get("/{card_id}/benefits")
def benefits(card_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get(db, user, card_id)
    data = c.catalogue.data if c.catalogue else {}
    rules = data.get("rules") or {}
    spend = _spend_profile(db, user)
    fit = []
    for cat, monthly in sorted(spend.items(), key=lambda kv: -kv[1]):
        e = estimate_card(_card_dict(c), monthly, cat, None)
        fit.append({"category": cat, "label": CATEGORIES.get(cat, cat), "monthly_spend": monthly,
                    "estimated_units": e.get("reward_units"), "estimated_value_inr": e.get("value_inr"),
                    "caveats": e.get("caveats", []), "incomplete": e.get("incomplete", [])})
    return {
        "currency": "INR", "card": card_out(c), "rules": rules, "benefits": rules.get("benefits", []),
        "redemption": data.get("redemption", []), "expiry": data.get("expiry"), "fees": data.get("fees"),
        "spend_fit": fit,
        "spend_fit_note": "Estimates what your average monthly spending by category (from your bank statement) would earn on this card. "
                          "It doesn't know which card you actually used for each payment.",
    }


class SpendIn(BaseModel):
    amount: float = Field(gt=0, le=100_000_000)
    category: str | None = None
    merchant: str | None = Field(default=None, max_length=80)


@router.post("/best-for-spend")
def best(body: SpendIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cards = db.query(UserCard).filter(UserCard.user_id == user.id).all()
    if not cards:
        raise DomainError("NO_CARDS", "Add at least one card to compare.", status_code=422)
    category = body.category
    inferred = False
    if not category and body.merchant:
        cat, _, _ = categorize(body.merchant, "debit")
        category, inferred = (cat if cat in SPEND_CATEGORIES else "other"), True
    if category and category not in CATEGORIES:
        raise DomainError("INVALID_CATEGORY", "Choose a valid category.", field="category")
    result = best_for_spend([_card_dict(c) for c in cards], body.amount, category, body.merchant)
    result["category_inferred"] = inferred
    result["category_label"] = CATEGORIES.get(category or "other")
    db.add(CalculationRun(user_id=user.id, kind="cards.best_for_spend", inputs=body.model_dump(),
                          outputs={"ranked": [r["card_id"] for r in result["ranked"]]}, formula_version=FORMULA_VERSION))
    audit(db, user.id, "recommendation.card", None, None, category=category)
    db.commit()
    return {"currency": "INR", **result}


@router.get("/insights/categories")
def category_insights(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Where a different existing card may earn more, based on spending categories (RD §13.3)."""
    cards = db.query(UserCard).filter(UserCard.user_id == user.id).all()
    spend = _spend_profile(db, user)
    rows = []
    if len(cards) >= 1:
        for cat, monthly in sorted(spend.items(), key=lambda kv: -kv[1]):
            if monthly < 500:
                continue
            r = best_for_spend([_card_dict(c) for c in cards], monthly, cat)
            if not r["ranked"]:
                continue
            top = r["ranked"][0]
            if not top["value_inr"]:
                continue
            runner = r["ranked"][1] if len(r["ranked"]) > 1 else None
            rows.append({
                "category": cat, "label": CATEGORIES.get(cat, cat), "monthly_spend": monthly,
                "best_card_id": top["card_id"], "best_card": top["card_name"], "best_value_inr": top["value_inr"],
                "next_card": runner["card_name"] if runner else None,
                "difference_inr": (top["value_inr"] - runner["value_inr"]) if runner else None,
                "caveats": top.get("caveats", []), "unranked_cards": [u["card_name"] for u in r["unranked"]],
            })
    return {"currency": "INR", "insights": rows,
            "note": "Based on your average monthly spending by category and each card's sample reward rules."}
