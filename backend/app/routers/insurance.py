"""Insurance journey + Emergency Mode (RD §15–16, S40–S47)."""

from collections import defaultdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import current_user
from app.errors import DomainError, NotFound
from app.models import Document, DocumentFact, FamilyMember, InsuranceProduct, PolicyMember, User, UserPolicy
from app.routers.documents import doc_out, fact_out
from app.services import profile_engine, slices
from app.services.catalogue import catalogue_meta
from app.services.recommend import insurance as rec

router = APIRouter(prefix="/insurance", tags=["insurance"])

TYPE_LABELS = {"health": "Health", "term_life": "Term life", "traditional_life": "Traditional life (endowment / money-back)",
               "travel": "Travel", "other": "Other"}

GENERAL_STEPS = {
    "hospitalisation": [
        "Inform your insurer or TPA as soon as possible — check the deadline in your policy.",
        "At a network hospital, ask the insurance desk for cashless treatment and share your policy details.",
        "At a non-network hospital, pay the bills and keep every original document for a reimbursement claim.",
        "Collect the discharge summary, final bill, payment receipts, prescriptions and investigation reports.",
        "Submit the claim form with documents within the time your policy allows.",
    ],
    "death": [
        "Inform the insurer and note the claim reference.",
        "Collect the death certificate and the policy document.",
        "The nominee submits the claim form with ID and bank details.",
    ],
}
DISCLAIMER = ("The insurer decides whether a claim is admissible. VITRAM shows what your policy documents say and "
              "can't guarantee approval.")


def _members_map(db: Session, user: User) -> dict[str, dict]:
    out = {"self": {"key": "self", "name": user.name.split(" ")[0] if user.name else "You", "relation": "self"}}
    for m in db.query(FamilyMember).filter(FamilyMember.user_id == user.id):
        out[m.id] = {"key": m.id, "name": m.name, "relation": m.relation}
    return out


def policy_brief(p: UserPolicy, members: dict) -> dict:
    return {
        "id": p.id, "document_id": p.document_id, "insurer": p.insurer, "product_name": p.product_name, "type": p.type,
        "type_label": TYPE_LABELS.get(p.type, p.type), "policy_ref_masked": p.policy_ref_masked,
        "start_date": p.start_date.isoformat() if p.start_date else None, "end_date": p.end_date.isoformat() if p.end_date else None,
        "premium": p.premium, "coverage": p.coverage, "status": p.status, "members_confirmed": p.members_confirmed,
        "members": [members.get(m.family_member_id or "self", {"key": m.family_member_id, "name": "Unknown", "relation": "?"}) for m in p.members],
    }


def _get_policy(db: Session, user: User, pid: str) -> UserPolicy:
    p = db.query(UserPolicy).filter(UserPolicy.id == pid, UserPolicy.user_id == user.id).first()
    if not p:
        raise NotFound("Policy")
    return p


@router.get("/overview")
def overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    members = _members_map(db, user)
    pols = db.query(UserPolicy).filter(UserPolicy.user_id == user.id, UserPolicy.status != "failed").all()
    today = date.today()
    by_type = defaultdict(list)
    for p in pols:
        by_type[p.type].append(policy_brief(p, members))
    matrix = []
    for key, m in members.items():
        covered = [p for p in pols if key in [pm.family_member_id or "self" for pm in p.members]]
        health = sum((p.coverage or {}).get("sum_insured") or 0 for p in covered if p.type == "health")
        life = sum((p.coverage or {}).get("sum_insured") or 0 for p in covered if p.type in ("term_life", "traditional_life"))
        matrix.append({**m, "policies": [{"id": p.id, "name": p.product_name, "type": p.type} for p in covered],
                       "health_cover": health, "life_cover": life})
    annual = 0.0
    unknown_premiums = 0
    for p in pols:
        prem = (p.premium or {}).get("amount")
        freq = (p.premium or {}).get("frequency", "annual")
        if prem is None:
            unknown_premiums += 1
            continue
        annual += prem * {"monthly": 12, "quarterly": 4, "half-yearly": 2, "half yearly": 2}.get(freq, 1)
    renewals = sorted([policy_brief(p, members) for p in pols if p.end_date and p.end_date >= today and (p.end_date - today).days <= 90],
                      key=lambda x: x["end_date"])
    processing = [doc_out(d) for d in db.query(Document).filter(Document.owner_user_id == user.id, Document.type == "insurance_policy",
                                                                Document.processing_status.in_(["queued", "processing", "failed"]))]
    return {"currency": "INR", "policies_by_type": [{"type": t, "label": TYPE_LABELS.get(t, t), "policies": v} for t, v in by_type.items()],
            "family_coverage": matrix, "annual_premium_total": round(annual, 2), "unknown_premiums": unknown_premiums,
            "upcoming_renewals": renewals, "processing": processing, "policy_count": len(pols)}


@router.get("/policies")
def list_policies(user: User = Depends(current_user), db: Session = Depends(get_db)):
    members = _members_map(db, user)
    return [policy_brief(p, members) for p in db.query(UserPolicy).filter(UserPolicy.user_id == user.id).order_by(UserPolicy.created_at.desc())]


@router.get("/policies/{pid}")
def policy_detail(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _get_policy(db, user, pid)
    members = _members_map(db, user)
    d = db.get(Document, p.document_id) if p.document_id else None
    facts = db.query(DocumentFact).filter(DocumentFact.document_id == p.document_id).all() if d else []
    grouped = defaultdict(list)
    for f in facts:
        grouped[f.fact_type].append(fact_out(f, d))
    fmap = {f.key: f for f in facts}

    def months(key):
        f = fmap.get(key)
        if not f or not isinstance(f.value, str):
            return None
        import re
        m = re.match(r"(\d+)\s*(month|year|day)", f.value.lower())
        if not m:
            return None
        n = int(m.group(1))
        return n * 12 if m.group(2) == "year" else (n if m.group(2) == "month" else None)

    waiting = []
    for key, label in (("ped_waiting_period", "Pre-existing conditions"), ("specific_disease_waiting_period", "Specific illnesses")):
        st = rec.ped_status(p.start_date, months(key))
        if st:
            waiting.append({"label": label, **st, "citation": fact_out(fmap[key], d)["citation"]})
    conflicts = [fact_out(f, d) for f in facts if f.state == "conflicted"]
    audit(db, user.id, "policy.viewed", "policy", p.id)
    db.commit()
    return {"currency": "INR", "policy": policy_brief(p, members), "document": doc_out(d) if d else None,
            "facts": dict(grouped), "waiting_status": waiting, "conflicts": conflicts,
            "family_options": list(members.values()), "disclaimer": DISCLAIMER}


class MembersIn(BaseModel):
    member_keys: list[str] = Field(min_length=1, max_length=10)


@router.put("/policies/{pid}/members")
def set_members(pid: str, body: MembersIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _get_policy(db, user, pid)
    valid = set(_members_map(db, user))
    if any(k not in valid for k in body.member_keys):
        raise DomainError("INVALID_MEMBERS", "One of the selected people wasn't found.", field="member_keys")
    db.query(PolicyMember).filter(PolicyMember.policy_id == p.id).delete()
    db.flush()
    db.expire(p, ["members"])
    for k in dict.fromkeys(body.member_keys):
        db.add(PolicyMember(policy_id=p.id, family_member_id=None if k == "self" else k))
    p.members_confirmed = True
    audit(db, user.id, "policy.members_set", "policy", p.id)
    db.flush()
    profile_engine.build_profile(db, user)
    db.commit()
    db.refresh(p)
    return policy_brief(p, _members_map(db, user))


@router.post("/policies/{pid}/confirm")
def confirm_policy(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _get_policy(db, user, pid)
    if not p.members_confirmed:
        raise DomainError("MEMBERS_REQUIRED", "Confirm who this policy covers first.", field="member_keys")
    p.status = "active"
    for f in db.query(DocumentFact).filter(DocumentFact.document_id == p.document_id, DocumentFact.state == "extracted"):
        f.state, f.user_verified = "confirmed", True
    audit(db, user.id, "policy.confirmed", "policy", p.id)
    db.commit()
    return policy_brief(p, _members_map(db, user))


@router.get("/catalogue")
def catalogue(type: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(InsuranceProduct)
    if type:
        q = q.filter(InsuranceProduct.type == type)
    return {"currency": "INR", "products": [{**r.data, "catalogue": catalogue_meta(r)} for r in q.order_by(InsuranceProduct.type)]}


class RecommendIn(BaseModel):
    type: Literal["health", "term_life", "traditional_life", "travel"]
    member_keys: list[str] = Field(min_length=1, max_length=8)
    sum_insured: float | None = Field(default=None, gt=0)
    budget_annual: float | None = Field(default=None, gt=0)
    need: str | None = Field(default=None, max_length=300)


@router.post("/recommend")
def recommend(body: RecommendIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    members = slices.insurance_members(db, user, body.member_keys)
    if len(members) != len(set(body.member_keys)):
        raise DomainError("INVALID_MEMBERS", "One of the selected people wasn't found.", field="member_keys")
    rows = db.query(InsuranceProduct).all()
    metas = {r.id: catalogue_meta(r) for r in rows}
    result = rec.recommend([r.data for r in rows], metas, body.model_dump(), members, slices.policies_for(db, user))
    audit(db, user.id, "recommendation.insurance", None, None, type=body.type, results=len(result["results"]))
    db.commit()
    return {"currency": "INR", **result}


class CompareIn(BaseModel):
    product_ids: list[str] = Field(default_factory=list, max_length=4)
    policy_ids: list[str] = Field(default_factory=list, max_length=3)
    member_keys: list[str] = Field(default_factory=lambda: ["self"], max_length=8)
    sum_insured: float | None = None


@router.post("/compare")
def compare(body: CompareIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if len(body.product_ids) + len(body.policy_ids) < 2:
        raise DomainError("TOO_FEW", "Pick at least two plans or policies to compare.")
    members = slices.insurance_members(db, user, body.member_keys)
    cols = []
    for pid in body.product_ids:
        r = db.get(InsuranceProduct, pid)
        if not r:
            raise NotFound("Insurance product")
        d = r.data
        res = d.get("restrictions", {})
        if d.get("reference_only"):
            cols.append({
                "kind": "catalogue", "id": r.id, "insurer": r.insurer, "product_name": r.product_name, "type": r.type,
                "coverage": {"sum_insured_options": None, "benefits": d.get("best_for", []), "room_rent": None, "sub_limits": []},
                "cost": {"amount": None, "label": "Check current official quote"},
                "restrictions": {}, "family_fit": [{"name": m["name"], "eligible": None, "age_known": m.get("age") is not None}
                                                   for m in members],
                "claims": None, "official_url": d.get("official_url"), "reference_only": True,
                "catalogue": catalogue_meta(r),
            })
            continue
        cols.append({
            "kind": "catalogue", "id": r.id, "insurer": r.insurer, "product_name": r.product_name, "type": r.type,
            "coverage": {"sum_insured_options": d.get("coverage", {}).get("sum_insured_options"), "benefits": d.get("coverage", {}).get("benefits", []),
                         "room_rent": d.get("coverage", {}).get("room_rent"), "sub_limits": res.get("sub_limits", [])},
            "cost": {**rec.indicative_premium(d, members, body.sum_insured), "label": "Indicative, not a quote"},
            "restrictions": {"initial_waiting_days": res.get("initial_waiting_days"), "ped_waiting_months": res.get("ped_waiting_months"),
                             "specific_disease_waiting_months": res.get("specific_disease_waiting_months"), "copay_pct": res.get("copay_pct"),
                             "deductible": res.get("deductible"), "exclusions": res.get("exclusions", [])},
            "family_fit": [{"name": m["name"], "eligible": rec._relation_ok(d["eligibility"].get("members", []), m["relation"])
                            and (m.get("age") is None or d["eligibility"]["age_min"] <= m["age"] <= d["eligibility"]["age_max"]),
                            "age_known": m.get("age") is not None} for m in members],
            "claims": d.get("claims"), "catalogue": catalogue_meta(r),
        })
    for pid in body.policy_ids:
        p = _get_policy(db, user, pid)
        facts = {f.key: f for f in db.query(DocumentFact).filter(DocumentFact.document_id == p.document_id)}
        doc = db.get(Document, p.document_id)

        def v(k):
            return facts[k].value if k in facts else None

        def cite(k):
            return fact_out(facts[k], doc)["citation"] if k in facts else None
        cols.append({
            "kind": "existing", "id": p.id, "insurer": p.insurer, "product_name": p.product_name, "type": p.type,
            "coverage": {"sum_insured": v("sum_insured"), "benefits": v("benefits") or [], "room_rent": v("room_rent_limit"),
                         "sub_limits": v("conditions") or []},
            "cost": {"amount": (p.premium or {}).get("amount"), "frequency": (p.premium or {}).get("frequency"), "label": "From your policy"},
            "restrictions": {"initial_waiting": v("initial_waiting_period"), "ped_waiting": v("ped_waiting_period"),
                             "specific_disease_waiting": v("specific_disease_waiting_period"), "copay_pct": v("copay"),
                             "deductible": v("deductible"), "exclusions": v("exclusions") or []},
            "family_fit": [{"name": m["name"], "eligible": m["key"] in [pm.family_member_id or "self" for pm in p.members], "age_known": True} for m in members],
            "claims": {"cashless_process": v("cashless_process"), "reimbursement_process": v("reimbursement_process"),
                       "intimation": v("claim_intimation"), "documents": v("claim_documents")},
            "citations": {k: cite(k) for k in ("sum_insured", "premium", "copay", "ped_waiting_period", "exclusions") if cite(k)},
            "source": "Your uploaded policy",
        })
    audit(db, user.id, "insurance.compare", None, None, n=len(cols))
    db.commit()
    return {"currency": "INR", "columns": cols, "members": members, "disclaimer": "Indicative premiums from sample data are not binding quotes."}


@router.get("/events")
def events(user: User = Depends(current_user)):
    return [{"key": k, "label": v["label"]} for k, v in rec.EVENT_TYPES.items()]


class EmergencyIn(BaseModel):
    member_key: str | None = None
    event: Literal["hospitalisation", "accident", "day_care", "death", "travel_medical"]
    question: str | None = Field(default=None, max_length=300)


def emergency_lookup(db: Session, user: User, member_key: str | None, event: str) -> dict:
    members = _members_map(db, user)
    if member_key is None:
        if len(members) > 1:
            raise DomainError("MEMBER_REQUIRED", "Who is this for? Choose the person first.", field="member_key", status_code=422)
        member_key = "self"
    if member_key not in members:
        raise NotFound("Family member")
    person = members[member_key]
    types = rec.EVENT_TYPES[event]["types"]
    pols = db.query(UserPolicy).filter(UserPolicy.user_id == user.id, UserPolicy.status != "failed").all()
    # Only the selected person's policies are retrieved (RD §16.1 step 29).
    mine = [p for p in pols if member_key in [pm.family_member_id or "self" for pm in p.members]]
    today = date.today()
    out = []
    for p in mine:
        d = db.get(Document, p.document_id) if p.document_id else None
        facts = {f.key: f for f in db.query(DocumentFact).filter(DocumentFact.document_id == p.document_id)} if d else {}

        def item(k):
            f = facts.get(k)
            return None if f is None else {"value": f.value, "citation": fact_out(f, d)["citation"], "state": f.state}
        reasons, status = [], "may_apply"
        if p.type not in types:
            status = "not_applicable"
            reasons.append(f"This is a {TYPE_LABELS.get(p.type, p.type).lower()} policy, which doesn't usually cover {rec.EVENT_TYPES[event]['label'].lower()}.")
        if p.end_date and p.end_date < today:
            status = "lapsed_or_expired"
            reasons.append(f"The policy period in the document ended on {p.end_date:%d %b %Y}. Check with the insurer whether it was renewed.")
        if p.start_date and p.start_date > today:
            status = "not_started"
            reasons.append(f"Cover starts on {p.start_date:%d %b %Y}.")
        waits = []
        for key, label in (("initial_waiting_period", "Initial waiting period"), ("ped_waiting_period", "Pre-existing conditions waiting period"),
                           ("specific_disease_waiting_period", "Specific illness waiting period")):
            f = facts.get(key)
            if f and isinstance(f.value, str):
                import re
                m = re.match(r"(\d+)\s*(day|month|year)", f.value.lower())
                if m:
                    n, unit = int(m.group(1)), m.group(2)
                    months = n * 12 if unit == "year" else (n if unit == "month" else None)
                    days = n if unit == "day" else None
                    st = None
                    if p.start_date:
                        if months:
                            st = rec.ped_status(p.start_date, months)
                        elif days:
                            from datetime import timedelta
                            ends = p.start_date + timedelta(days=days)
                            st = {"ends_on": ends.isoformat(), "running": today < ends}
                    waits.append({"label": label, "value": f.value, "status": st, "citation": fact_out(f, d)["citation"]})
        if status == "may_apply":
            reasons.append(f"Covers {person['name']} and is a {TYPE_LABELS.get(p.type, p.type).lower()} policy.")
            if any(w["status"] and w["status"]["running"] for w in waits):
                reasons.append("A waiting period is still running — some conditions may not be covered yet.")
        docs_needed = item("claim_documents")
        steps_source = "policy" if (facts.get("cashless_process") or facts.get("reimbursement_process") or facts.get("claim_process")) else "general"
        out.append({
            "policy": policy_brief(p, members), "status": status, "reasons": reasons,
            "coverage": {"sum_insured": item("sum_insured"), "copay": item("copay"), "room_rent": item("room_rent_limit"),
                         "deductible": item("deductible"), "benefits": item("benefits")},
            "waiting_periods": waits,
            "exclusions": item("exclusions"), "conditions": item("conditions"),
            "claim": {
                "intimation": item("claim_intimation"), "cashless": item("cashless_process"),
                "reimbursement": item("reimbursement_process"), "process": item("claim_process"),
                "documents": docs_needed,
                "general_steps": GENERAL_STEPS.get("death" if event == "death" else "hospitalisation") if steps_source == "general" else None,
                "steps_source": steps_source,
            },
            "contacts": {"tpa": item("tpa"), "helpline": item("helpline"), "email": item("claims_email"), "insurer": p.insurer},
        })
    order = {"may_apply": 0, "not_started": 1, "lapsed_or_expired": 2, "not_applicable": 3}
    out.sort(key=lambda x: order.get(x["status"], 9))
    other_people = [m["name"] for k, m in members.items() if k != member_key and any(k in [pm.family_member_id or "self" for pm in p.members] for p in pols)]
    return {
        "person": person, "event": {"key": event, **rec.EVENT_TYPES[event]}, "policies": out,
        "applicable_count": sum(1 for x in out if x["status"] == "may_apply"),
        "other_people_with_policies": other_people,
        "disclaimer": DISCLAIMER,
    }


@router.post("/emergency")
def emergency(body: EmergencyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    result = emergency_lookup(db, user, body.member_key, body.event)
    audit(db, user.id, "insurance.emergency", "family_member", body.member_key, event=body.event)
    db.commit()
    return {"currency": "INR", **result}
