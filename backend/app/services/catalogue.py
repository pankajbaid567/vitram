"""Catalogue service (RD §12.3, §18.1): curated JSON → tables, with provenance on every record.

The adapter boundary is `load_catalogues()`; a real provider can replace the
JSON source later without touching recommendation or calculation code.
"""

import json
from datetime import date
from pathlib import Path

from app.config import get_settings
from app.db import SessionLocal
from app.models import CardProduct, InsuranceProduct, LoanProduct

CATALOGUE_DIR = Path(__file__).resolve().parent.parent / "catalogues"


def _read(name: str) -> dict:
    return json.loads((CATALOGUE_DIR / name).read_text())


def load_catalogues() -> None:
    db = SessionLocal()
    try:
        loans = _read("loans.json")
        for p in loans["products"]:
            row = db.get(LoanProduct, p["id"]) or LoanProduct(id=p["id"])
            row.lender, row.product_name, row.category, row.secured = p["lender"], p["product_name"], p["category"], p["secured"]
            row.data, row.source, row.is_mock = p, loans["meta"]["source"], loans["meta"]["is_mock"]
            row.updated_at = date.fromisoformat(loans["meta"]["last_updated"])
            db.merge(row)
        for filename in ("cards.json", "market_cards.json"):
            cards = _read(filename)
            for p in cards["products"]:
                row = db.get(CardProduct, p["id"]) or CardProduct(id=p["id"])
                row.issuer, row.card_name, row.data = p["issuer"], p["card_name"], p
                row.source, row.is_mock = cards["meta"]["source"], cards["meta"]["is_mock"]
                row.updated_at = date.fromisoformat(cards["meta"]["last_updated"])
                db.merge(row)
        for filename in ("insurance.json", "market_insurance.json"):
            ins = _read(filename)
            for p in ins["products"]:
                row = db.get(InsuranceProduct, p["id"]) or InsuranceProduct(id=p["id"])
                row.insurer, row.product_name, row.type, row.data = p["insurer"], p["product_name"], p["type"], p
                row.source, row.is_mock = ins["meta"]["source"], ins["meta"]["is_mock"]
                row.updated_at = date.fromisoformat(ins["meta"]["last_updated"])
                db.merge(row)
        db.commit()
    finally:
        db.close()


def catalogue_meta(row) -> dict:
    """RD §20.1: source + last_updated + mock/live; RD §26: stale marker."""
    age = (date.today() - row.updated_at).days
    return {
        "source": row.source,
        "last_updated": row.updated_at.isoformat(),
        "is_mock": row.is_mock,
        "is_stale": age > get_settings().catalogue_stale_days,
    }
