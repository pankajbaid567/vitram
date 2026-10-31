"""Loan journey (RD §12, S10–S16)."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db import get_db
from app.deps import current_user
from app.errors import DomainError, NotFound
from app.models import Document, DocumentFact, LoanProduct, User, UserLoan
from app.routers.documents import fact_out, get_doc
from app.services import calculations, slices
from app.services.catalogue import catalogue_meta
from app.services.finance import what_if
from app.services.finance.emi import schedule
from app.services.finance.loan_cost import loan_cost_breakdown
from app.services.recommend import loans as rec

router = APIRouter(prefix="/loans", tags=["loans"])

Purpose = Literal["home", "vehicle", "education", "medical", "wedding", "travel", "home_renovation",
                  "debt_consolidation", "personal", "other"]


def product_out(row: LoanProduct) -> dict:
    return {**row.data, "catalogue": catalogue_meta(row)}


@router.get("/catalogue")
def catalogue(category: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(LoanProduct)
    if category:
        q = q.filter(LoanProduct.category == category)
    return {"currency": "INR", "products": [product_out(r) for r in q.order_by(LoanProduct.category, LoanProduct.lender)]}


@router.get("/products/{product_id}")
def product(product_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(LoanProduct, product_id)
    if not row:
        raise NotFound("Loan product")
    return {"currency": "INR", "product": product_out(row)}


class Collateral(BaseModel):
    available: bool | None = None
    type: Literal["property", "vehicle", "gold", "fixed_deposit", "other"] | None = None
    value: float | None = Field(default=None, gt=0, le=10_000_000_000)


class LoanIntent(BaseModel):
    purpose: Purpose
    amount: float = Field(gt=0, le=1_000_000_000)
    tenure_months: int | None = Field(default=None, ge=1, le=360)
    collateral: Collateral | None = None
    emi_comfort: float | None = Field(default=None, gt=0)
    prepayment_important: bool = False
    monthly_income_override: float | None = Field(default=None, gt=0)


def _profile_for(db: Session, user: User, intent: LoanIntent) -> dict:
    prof = slices.loan_slice(db, user)
    if intent.monthly_income_override:
        prof["monthly_income"] = intent.monthly_income_override
        prof["monthly_income_state"] = "confirmed"
        prof["monthly_income_source"] = "You entered this for this search"
    return prof


def run_recommend(db: Session, user: User, intent: LoanIntent) -> dict:
    rows = db.query(LoanProduct).all()
    metas = {r.id: catalogue_meta(r) for r in rows}
    prof = _profile_for(db, user, intent)
    result = rec.recommend([r.data for r in rows], metas, intent.model_dump(), prof, get_settings().default_gst_on_fees_pct)
    audit(db, user.id, "loan.recommend", "loan_intent", None, purpose=intent.purpose, results=len(result["results"]))
    run_id = calculations.record(db, user.id, "loan.recommend", {"intent": intent.model_dump(), "profile": prof},
                                 {"ranked": [r["product_id"] for r in result["results"]]}, rec.FORMULA_VERSION)
    db.commit()
    return {"currency": "INR", "calculation_id": run_id, **result}


@router.post("/recommend")
def recommend(intent: LoanIntent, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return run_recommend(db, user, intent)


class CompareIn(BaseModel):
    product_ids: list[str] = Field(min_length=2, max_length=4)
    intent: LoanIntent


@router.post("/compare")
def compare(body: CompareIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = [db.get(LoanProduct, pid) for pid in body.product_ids]
    if any(r is None for r in rows):
        raise NotFound("Loan product")
    metas = {r.id: catalogue_meta(r) for r in rows}
    prof = _profile_for(db, user, body.intent)
    gst = get_settings().default_gst_on_fees_pct
    evals = []
    for r in rows:
        e = rec.evaluate(r.data, body.intent.model_dump(), prof, gst)
        rules = {c["key"]: c.get("rule") for c in r.data.get("contingent", [])}
        evals.append({
            "product_id": r.id, "lender": r.lender, "product_name": r.product_name, "category": r.category,
            "eligible": e["eligible"], "excluded_reasons": [rec.EXCLUDE_TEXT.get(x, x) for x in e["excluded_reasons"]],
            "price": {"indicative_rate": r.data["pricing"].get("indicative_rate"), "rate_range": [r.data["pricing"].get("rate_min"), r.data["pricing"].get("rate_max")],
                      "monthly_emi": e["cost"]["monthly_emi"], "scheduled_interest": e["cost"]["scheduled_interest"],
                      "upfront_charges_total": e["cost"]["upfront_charges_total"], "scheduled_total_outflow": e["cost"]["scheduled_total_outflow"],
                      "annualized_cost_pct": e["cost"]["annualized_cost_pct"], "missing": e["cost"]["missing"]},
            "flexibility": {"tenure_range": [r.data["repayment"]["tenure_min"], r.data["repayment"]["tenure_max"]],
                            "interest_type": r.data["pricing"].get("interest_type"),
                            "part_prepayment": rules.get("part_prepayment"), "foreclosure": rules.get("foreclosure")},
            "eligibility_fit": {"matched": e["matched"], "unknown": e["unknown_conditions"]},
            "collateral": r.data["eligibility"].get("collateral", "none"),
            "warnings": r.data.get("clauses", []),
            "why": rec._why(e, body.intent.model_dump(), prof, None) if e["eligible"] else [],
            "cautions": rec._cautions(e, body.intent.model_dump()),
            "tenure_months": e["tenure_months"],
            "catalogue": metas[r.id],
        })
    run_id = calculations.record(db, user.id, "loan.compare", {"intent": body.intent.model_dump(), "product_ids": body.product_ids},
                                 {"products": [{"id": e["product_id"], "emi": e["price"]["monthly_emi"]} for e in evals]}, rec.FORMULA_VERSION)
    audit(db, user.id, "loan.compare", None, None, products=body.product_ids)
    db.commit()
    return {"currency": "INR", "calculation_id": run_id, "intent": body.intent.model_dump(), "profile_used": prof, "products": evals}


class CalcIn(BaseModel):
    kind: Literal["cost", "tenure_change", "amount_change", "prepayment", "missed_payment", "rate_change", "affordability"]
    product_id: str | None = None
    user_loan_id: str | None = None
    principal: float | None = Field(default=None, gt=0)
    annual_rate_pct: float | None = Field(default=None, ge=0, le=60)
    tenure_months: int | None = Field(default=None, ge=1, le=480)
    new_tenure_months: int | None = Field(default=None, ge=1, le=480)
    new_principal: float | None = Field(default=None, gt=0)
    prepay_amount: float | None = Field(default=None, gt=0)
    after_month: int | None = Field(default=None, ge=1)
    mode: Literal["reduce_tenure", "reduce_emi"] = "reduce_tenure"
    days_late: int = Field(default=30, ge=1, le=365)
    new_rate_pct: float | None = Field(default=None, ge=0, le=60)
    hold: Literal["emi", "tenure"] = "emi"
    gst_pct: float | None = Field(default=None, ge=0, le=40)
    late_rule_override: dict | None = None
    prepayment_rule_override: dict | None = None
    include_schedule: bool = False

    @model_validator(mode="after")
    def _need_terms(self):
        if self.kind != "affordability" and not (self.product_id or self.user_loan_id) and self.annual_rate_pct is None:
            raise ValueError("Give a product, a documented loan, or the interest rate")
        return self


def _terms(db: Session, user: User, body: CalcIn) -> dict:
    if body.product_id:
        row = db.get(LoanProduct, body.product_id)
        if not row:
            raise NotFound("Loan product")
        d = row.data
        return {"rate": body.annual_rate_pct if body.annual_rate_pct is not None else d["pricing"]["indicative_rate"],
                "charges": d.get("charges", []), "contingent": d.get("contingent", []), "catalogue": catalogue_meta(row),
                "source": "catalogue"}
    if body.user_loan_id:
        loan = db.query(UserLoan).filter(UserLoan.id == body.user_loan_id, UserLoan.user_id == user.id).first()
        if not loan:
            raise NotFound("Loan")
        t = loan.terms or {}
        return {"rate": body.annual_rate_pct if body.annual_rate_pct is not None else loan.rate,
                "principal": loan.principal, "tenure": loan.tenure_months,
                "charges": t.get("charges", []), "contingent": t.get("contingent", []), "source": "document",
                "document_id": loan.source_document_id}
    return {"rate": body.annual_rate_pct, "charges": [], "contingent": [], "source": "user_input"}


@router.post("/calculate")
def calculate(body: CalcIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _terms(db, user, body)
    gst = body.gst_pct if body.gst_pct is not None else get_settings().default_gst_on_fees_pct
    principal = body.principal or t.get("principal")
    tenure = body.tenure_months or t.get("tenure")
    rate = t["rate"]
    if body.kind != "affordability" and (principal is None or tenure is None or rate is None):
        missing = [n for n, v in (("loan amount", principal), ("tenure", tenure), ("interest rate", rate)) if v is None]
        raise DomainError("NOT_COMPUTABLE", f"Add the {', '.join(missing)} to run this calculation.", status_code=422)
    rules = {c["key"]: c.get("rule") for c in t["contingent"]}
    if body.kind == "cost":
        out = loan_cost_breakdown(principal, rate, tenure, t["charges"], t["contingent"], gst)
        if body.include_schedule:
            out["schedule"] = schedule(principal, rate, tenure)
        version = out["formula_version"]
    elif body.kind == "tenure_change":
        out = what_if.tenure_change(principal, rate, tenure, body.new_tenure_months or tenure)
        version = out["formula_version"]
    elif body.kind == "amount_change":
        out = what_if.amount_change(principal, rate, tenure, body.new_principal or principal)
        version = out["formula_version"]
    elif body.kind == "prepayment":
        if not body.prepay_amount or not body.after_month:
            raise DomainError("VALUE_REQUIRED", "Enter the prepayment amount and the month.", field="prepay_amount")
        rule = body.prepayment_rule_override or rules.get("part_prepayment")
        try:
            out = what_if.prepayment(principal, rate, tenure, body.prepay_amount, body.after_month, body.mode, rule, gst)
        except ValueError as exc:
            raise DomainError("INVALID_INPUT", str(exc), field="after_month") from exc
        version = out["formula_version"]
    elif body.kind == "missed_payment":
        from app.services.finance.emi import emi as emi_fn
        rule = body.late_rule_override or rules.get("late_payment")
        out = what_if.missed_payment(emi_fn(principal, rate, tenure), rule, body.days_late, gst)
        version = out["formula_version"]
    elif body.kind == "rate_change":
        if body.new_rate_pct is None:
            raise DomainError("VALUE_REQUIRED", "Enter the new interest rate.", field="new_rate_pct")
        out = what_if.rate_change(principal, rate, tenure, body.new_rate_pct, body.hold)
        version = out["formula_version"]
    else:
        from app.services.finance.emi import emi as emi_fn
        s = slices.emi_slice(db, user)
        new = emi_fn(principal, rate, tenure) if principal and rate is not None and tenure else None
        if new is None:
            raise DomainError("NOT_COMPUTABLE", "Add the loan amount, rate and tenure.", status_code=422)
        out = what_if.new_emi_affordability(s["monthly_income"], s["existing_emis"], new, s["avg_monthly_non_emi_spend"])
        version = out["formula_version"]
    out["terms_source"] = t["source"]
    if t.get("catalogue"):
        out["catalogue"] = t["catalogue"]
    run_id = calculations.record(db, user.id, f"loan.{body.kind}", body.model_dump(),
                                 {k: v for k, v in out.items() if k != "schedule"}, version)
    audit(db, user.id, "calculation.run", "calculation", run_id, kind=body.kind)
    db.commit()
    return {"currency": "INR", "precision": 2, "calculation_id": run_id, "result": out}


@router.get("/documents")
def loan_documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.owner_user_id == user.id, Document.type == "loan_document").order_by(Document.upload_time.desc()).all()
    from app.routers.documents import doc_out
    return [doc_out(d) for d in docs]


@router.get("/documents/{doc_id}")
def analysis(doc_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Loan at a glance + Real Cost from extracted terms + clauses with sources (RD §12.9)."""
    from app.routers.documents import doc_out
    d = get_doc(db, user, doc_id)
    if d.type != "loan_document":
        raise NotFound("Loan document")
    facts = db.query(DocumentFact).filter(DocumentFact.document_id == d.id).all()
    terms_fact = next((f for f in facts if f.key == "_terms"), None)
    terms = dict(terms_fact.value) if terms_fact else {}
    # user corrections to core facts win
    for f in facts:
        if f.user_verified and f.key in ("principal", "annual_rate_pct", "tenure_months", "stated_emi"):
            terms[f.key] = f.value
    cost, cost_missing = None, []
    for k, label in (("principal", "loan amount"), ("annual_rate_pct", "interest rate"), ("tenure_months", "tenure")):
        if terms.get(k) is None:
            cost_missing.append(label)
    if not cost_missing:
        cost = loan_cost_breakdown(float(terms["principal"]), float(terms["annual_rate_pct"]), int(terms["tenure_months"]),
                                   terms.get("charges"), terms.get("contingent"), get_settings().default_gst_on_fees_pct)
        if terms.get("stated_emi"):
            diff = abs(cost["monthly_emi"] - float(terms["stated_emi"]))
            cost["emi_check"] = {"stated": terms["stated_emi"], "calculated": cost["monthly_emi"], "matches": diff <= max(2, 0.005 * cost["monthly_emi"])}
        if terms.get("stated_apr_pct") is not None:
            cost["stated_apr_pct"] = terms["stated_apr_pct"]
    audit(db, user.id, "document.facts_viewed", "document", d.id)
    db.commit()
    loan = db.query(UserLoan).filter(UserLoan.source_document_id == d.id).first()
    return {
        "currency": "INR",
        "document": doc_out(d),
        "user_loan_id": loan.id if loan else None,
        "facts": [fact_out(f, d) for f in facts if f.key != "_terms"],
        "terms": {k: v for k, v in terms.items() if k not in ("charges", "contingent", "clauses")},
        "clauses": terms.get("clauses", []),
        "cost": cost,
        "cost_missing": cost_missing,
    }
