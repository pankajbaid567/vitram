"""Shared response contracts (RD §20.1)."""

from typing import Any, Literal

from pydantic import BaseModel, Field


def r2(x: float | None) -> float | None:
    return None if x is None else round(float(x) + 0.0, 2)


class Money(BaseModel):
    amount: float
    currency: Literal["INR"] = "INR"


def money(x: float | None) -> Money | None:
    return None if x is None else Money(amount=r2(x))


class SourceCitation(BaseModel):
    """RD §19.1."""

    document_id: str
    document_type: str
    document_name: str | None = None
    page: int | None = None
    section: str | None = None
    snippet: str | None = None
    fact_key: str | None = None
    confidence: float | None = None
    user_verified: bool = False


class CatalogueMeta(BaseModel):
    source: str
    last_updated: str
    is_mock: bool
    is_stale: bool = False


class Calculation(BaseModel):
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    formula_version: str
    assumptions: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
